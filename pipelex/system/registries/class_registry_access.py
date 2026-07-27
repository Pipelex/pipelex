"""Process-global access to the active class registry, with an optional library-scoping resolver.

This module deliberately sits *below* both hubs and imports nothing from ``pipelex``, so any layer
can import it directly. That is not stylistic: ``pipelex.core.concepts.concept`` needs the active
class registry and is itself inside ``runtime_hub``'s import closure
(``runtime_hub`` -> ``cogt.llm.llm_worker_abstract`` -> ``system.telemetry.otel_factory`` ->
``core.pipes.pipe_output`` -> ``core.stuffs.stuff`` -> ``core.concepts.concept``), so it cannot
import ``runtime_hub`` at module level without forming a cycle. Hosting the accessor here is what
lets those modules use a plain top-level import instead of a lazy ``importlib`` shim.

``pipelex.runtime_hub.get_class_registry`` is the public accessor and delegates here; prefer it
everywhere except inside this module's own import closure.

Scoping: a run may pin a per-library ClassRegistry (a workflow's own registry) rather than the
process-global Kajson one. Resolving *which* library is current is interpreter-layer knowledge, so
the runtime layer holds only a slot — ``pipelex.interpreter_hub.set_interpreter_hub`` installs the real
resolver at boot. Unresolved, or with no library pinned, callers get the process-global registry.
"""

from collections.abc import Callable

from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager


def _no_library_scoping() -> ClassRegistryAbstract | None:
    """Core default resolver: with no InterpreterHub installed there is no per-library scoping."""
    return None


class ClassRegistryScoping:
    """Process-global slot holding the library-scoped class-registry resolver.

    Mirrors the ``HubSlot.ISOLATED_EXECUTION_PROBE`` pattern: a defaulted callable that a higher
    layer replaces at boot, never an unset attribute — so a process that only ever builds a
    RuntimeHub (the doctor path, most unit tests) degrades to the process-global registry instead
    of raising. Reached through the ``class_registry_scoping`` module singleton below, in the same
    style as ``config_manager``.
    """

    def __init__(self) -> None:
        self._resolver: Callable[[], ClassRegistryAbstract | None] = _no_library_scoping

    def install(self, *, resolver: Callable[[], ClassRegistryAbstract | None]) -> None:
        self._resolver = resolver

    def reset(self) -> None:
        self._resolver = _no_library_scoping

    def resolve(self) -> ClassRegistryAbstract | None:
        return self._resolver()


class_registry_scoping = ClassRegistryScoping()


def get_class_registry() -> ClassRegistryAbstract:
    """Return the active class registry, respecting per-workflow library scoping.

    When a library_id is set in the current async context (e.g. inside a Temporal workflow),
    returns the library's scoped ClassRegistry. Otherwise, returns the global registry.
    """
    scoped_class_registry = class_registry_scoping.resolve()
    if scoped_class_registry is not None:
        return scoped_class_registry
    return KajsonManager.get_class_registry()
