"""The libraries a process loads from a run's concepts alone, to type the run's data where the run's own library is not held.

A run's data crosses a process boundary as a working memory dumped for transport, beside the concepts and domains of the
run's crate with none of its pipes (`LibraryCrate.concepts_only`). A step that renders that data in another process, such
as the print stage of a `PipeDocGen` step or the leaf of an LLM prompt in an activity on a worker, types it again: in the
run's own library when its process holds it, such as in a local run, so the data keeps the classes the run built it with,
and otherwise in a library loaded from the concepts alone. Loading a crate builds its concepts' classes, which costs more
than the render, so that library is kept, by the concepts' fingerprint, for the renders that follow (`ConceptsLibraryCache`).
"""

import threading
import uuid
from collections import OrderedDict
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any, NamedTuple

from pipelex.interpreter_hub import get_current_library_id_or_none, get_library_manager, scoped_current_library
from pipelex.libraries.library_crate import LibraryCrate

_CONCEPTS_LIBRARY_PREFIX = "concepts_typing"
# How many libraries typing a run's data this process keeps once no render uses them: one per set of concepts, so a
# worker rendering for a handful of methods loads each one's concepts once, and one rendering for many keeps the ones it
# used last. A library a render is using is never torn down, however many there are.
_CONCEPTS_LIBRARY_CAPACITY = 8


class _ConceptsLibrary(NamedTuple):
    library_id: str
    users: int


class ConceptsLibraryCache:
    """The libraries this process loaded from the concepts of a run's crate to type the run's data, by fingerprint.

    Loading a crate builds its concepts' classes, which costs more than the render, so a library is kept after its render
    for the next render typing data with the same concepts, such as the next step of the same method. Libraries no render
    is using are torn down beyond the capacity, the least recently used first. A library torn down by someone else, such
    as by the library manager's teardown of every library, is loaded again.
    """

    def __init__(self, *, capacity: int) -> None:
        self._capacity = capacity
        self._lock = threading.Lock()
        self._libraries: OrderedDict[str, _ConceptsLibrary] = OrderedDict()

    @contextmanager
    def library_for(self, *, concepts_crate: LibraryCrate) -> Generator[str, None, None]:
        """A library holding the crate's concepts, held for the block, the one kept for its fingerprint or one loaded for it."""
        library_id = self._acquire(concepts_crate=concepts_crate)
        try:
            yield library_id
        finally:
            self._release(fingerprint=concepts_crate.fingerprint)

    def held_library_ids(self) -> list[str]:
        """The libraries kept, in use or not, the least recently used first."""
        with self._lock:
            return [concepts_library.library_id for concepts_library in self._libraries.values()]

    def release_idle(self) -> None:
        """Tear down every library kept that no render is using."""
        with self._lock:
            idle = [fingerprint for fingerprint, concepts_library in self._libraries.items() if concepts_library.users <= 0]
            to_tear_down = [self._libraries.pop(fingerprint).library_id for fingerprint in idle]
        for library_id in to_tear_down:
            get_library_manager().teardown(library_id=library_id)

    def _acquire(self, *, concepts_crate: LibraryCrate) -> str:
        library_manager = get_library_manager()
        fingerprint = concepts_crate.fingerprint
        with self._lock:
            kept = self._libraries.get(fingerprint)
            if kept is not None and library_manager.is_crate_loaded(library_id=kept.library_id, fingerprint=fingerprint):
                self._libraries[fingerprint] = kept._replace(users=kept.users + 1)
                self._libraries.move_to_end(fingerprint)
                return kept.library_id
            library_id, _ = library_manager.open_library(library_id=f"{_CONCEPTS_LIBRARY_PREFIX}_{uuid.uuid4().hex}")
            try:
                # The crate's concepts were validated where the run's method was loaded.
                library_manager.load_from_crate(library_id=library_id, crate=concepts_crate, is_crate_prevalidated=True)
            except BaseException:
                library_manager.teardown(library_id=library_id)
                raise
            # A library kept under this fingerprint and torn down by someone else is replaced.
            self._libraries[fingerprint] = _ConceptsLibrary(library_id=library_id, users=1)
            self._libraries.move_to_end(fingerprint)
            return library_id

    def _release(self, *, fingerprint: str) -> None:
        to_tear_down: list[str] = []
        with self._lock:
            kept = self._libraries.get(fingerprint)
            if kept is not None:
                self._libraries[fingerprint] = kept._replace(users=kept.users - 1)
            idle = [kept_fingerprint for kept_fingerprint, concepts_library in self._libraries.items() if concepts_library.users <= 0]
            for kept_fingerprint in idle[: max(0, len(idle) - self._capacity)]:
                to_tear_down.append(self._libraries.pop(kept_fingerprint).library_id)
        for library_id in to_tear_down:
            get_library_manager().teardown(library_id=library_id)


#: The libraries this process keeps to type a run's data from its concepts.
CONCEPTS_LIBRARIES = ConceptsLibraryCache(capacity=_CONCEPTS_LIBRARY_CAPACITY)


@contextmanager
def typed_by_run_concepts(*, crate_fingerprint: str, concepts_crate: Mapping[str, Any]) -> Generator[None, None, None]:
    """Make current a library whose concepts type the run's data: the run's own when current, or one holding its concepts.

    The current library is the run's own in the process that loaded the run's method, so its concepts' classes are the
    ones the data was built with. Anywhere else, such as in an activity on a worker, the data is typed in a library loaded
    from the run's concepts alone, which reads no file, and which this process keeps for the renders that follow.

    Args:
        crate_fingerprint: The fingerprint of the run's whole crate, by which a process holding it renders in it.
        concepts_crate: The concepts and domains of the run's crate, with none of its pipes, as JSON.
    """
    library_manager = get_library_manager()
    current_library_id = get_current_library_id_or_none()
    if current_library_id is not None and library_manager.is_crate_loaded(library_id=current_library_id, fingerprint=crate_fingerprint):
        yield
        return
    concepts_only_crate = LibraryCrate.model_validate(concepts_crate)
    with CONCEPTS_LIBRARIES.library_for(concepts_crate=concepts_only_crate) as library_id, scoped_current_library(library_id=library_id):
        yield
