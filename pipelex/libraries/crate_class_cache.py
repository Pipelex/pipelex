"""The concepts and structure classes a process built for a crate, kept so a later load of the same crate builds none.

A trusted crate load spends most of its time building each structured concept's class with pydantic, and a hosted
worker loads the same crate again and again: every run of a stored method, every batch branch, which receives its
parent's crate unchanged, and every replay of a workflow evicted from the worker's cache. Each of those loads runs on
the workflow thread, inside the Temporal SDK's 2 s deadlock window, so the classes are built once per process and
handed to every later load of the crate (`wip/workflow-thread-under-load/design.md`, Part 2).

**What makes a hit correct.** The classes a load builds are a function of three things: the crate, the class registry
the load starts from, which a generated class's base and a reused class are read from, and the other concepts the
library already holds, which a forward reference may resolve to. So an entry is keyed by the crate's fingerprint,
records the registry it was built under, and is only built from, and only served to, a load into a library holding no
concept but the natives: a fresh library, which is what a workflow and a scoped hydration open. A load whose registry
differs from the entry's misses and builds its own classes.

**What makes sharing safe.** A run registers the cached classes into its own scoped registry, so tearing its library
down forgets them there and nowhere else. Nothing writes to a structure class after its load: an entry is kept only
when every class it holds is complete, so the rebuild every load still runs returns at once on a cached class. The
concept objects are copied on the way in and on the way out, since a library holds its concepts as mutable models.

**Bound and concurrency.** The cache holds at most `[interpreter.crate_class_cache] max_classes` classes over all its
entries, evicting the least recently used crate first; zero turns it off. Two loads of one crate that miss together
both build, and the first to finish is kept: the second keeps the classes it built for its own run, and every later
load gets the first's. Lookups and inserts take one lock, held only for dictionary work.
"""

import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from pydantic import BaseModel

from pipelex import log
from pipelex.core.concepts.concept import Concept


class CrateClasses(NamedTuple):
    """What a load of a crate built: its concepts, and the classes it registered, by registry name."""

    concepts: list[Concept]
    classes: dict[str, type[Any]]


class _CacheEntry(NamedTuple):
    seed: dict[str, type[Any]]
    built: CrateClasses


def _copied(*, concepts: Sequence[Concept]) -> list[Concept]:
    return [concept.model_copy() for concept in concepts]


class CrateClassCache:
    """The concepts and classes built per crate in this process, least recently used first out; one per process (`CRATE_CLASS_CACHE`)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._class_count = 0

    def lookup(self, *, fingerprint: str, seed: Mapping[str, type[Any]]) -> CrateClasses | None:
        """The concepts and classes built for the crate under the same starting registry, or None.

        Args:
            fingerprint: The crate's fingerprint.
            seed: The class registry the load starts from, by name.

        Returns:
            Copies of the concepts and the shared classes to register, or None on a miss.
        """
        with self._lock:
            entry = self._entries.get(fingerprint)
            if entry is None or entry.seed != seed:
                return None
            self._entries.move_to_end(fingerprint)
            return CrateClasses(concepts=_copied(concepts=entry.built.concepts), classes=dict(entry.built.classes))

    def insert(self, *, fingerprint: str, seed: Mapping[str, type[Any]], built: CrateClasses, max_classes: int) -> None:
        """Keep what a load built for a crate, unless an entry built under the same registry is already kept.

        An entry holding an incomplete class is not kept: a later load's rebuild would write to it.

        Args:
            fingerprint: The crate's fingerprint.
            seed: The class registry the load started from, by name.
            built: The concepts the load made and the classes it registered.
            max_classes: The most classes the cache holds over all its entries; zero keeps nothing.
        """
        for structure_class in built.classes.values():
            if issubclass(structure_class, BaseModel) and not structure_class.__pydantic_complete__:
                log.debug("Kept no classes for a crate with an incomplete structure class", fields={"crate_fingerprint": fingerprint})
                return
        size = max(len(built.classes), 1)
        if size > max_classes:
            return
        with self._lock:
            kept = self._entries.get(fingerprint)
            if kept is not None:
                if kept.seed == seed:
                    self._entries.move_to_end(fingerprint)
                    return
                self._forget(fingerprint=fingerprint)
            self._entries[fingerprint] = _CacheEntry(
                seed=dict(seed),
                built=CrateClasses(concepts=_copied(concepts=built.concepts), classes=dict(built.classes)),
            )
            self._class_count += size
            while self._class_count > max_classes:
                oldest_fingerprint = next(iter(self._entries))
                self._forget(fingerprint=oldest_fingerprint)

    def clear(self) -> None:
        """Forget every entry."""
        with self._lock:
            self._entries.clear()
            self._class_count = 0

    def fingerprints(self) -> list[str]:
        """The fingerprints of the crates kept, least recently used first."""
        with self._lock:
            return list(self._entries)

    def _forget(self, *, fingerprint: str) -> None:
        entry = self._entries.pop(fingerprint)
        self._class_count -= max(len(entry.built.classes), 1)


CRATE_CLASS_CACHE = CrateClassCache()
