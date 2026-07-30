"""Process-global access to the active class registry, with an optional library-scoping resolver.

This module deliberately sits *below* both hubs and imports nothing from ``pipelex``, so any layer
can import it directly. That is not stylistic: a module that needs the active class registry may be
one ``runtime_hub`` cannot be imported *from*, and hosting the accessor here is what lets it use a
plain top-level import instead of a lazy ``importlib`` shim.

Exactly one module needs that today, and the constraint is a **static-analysis** cycle rather than a
runtime one — measure before restating it. ``pipe_machinery.pipe_abstract`` decorates graph-registry
entries with a concept's JSON Schema. It is *not* in ``runtime_hub``'s runtime import closure (a
clean-interpreter probe after ``import pipelex.runtime_hub`` shows it, ``pipe_run.pipe_job`` and
``plugins.orchestrator_registry`` all absent — those edges are ``TYPE_CHECKING``-only). But pyright's
``reportImportCycles`` counts ``TYPE_CHECKING`` edges, so importing **either** hub there is a hard
type-check failure via ``runtime_hub`` -> ``plugins.orchestrator_registry`` -> ``pipe_run.pipe_job``
-> ``pipe_machinery.pipe_abstract``, and a deferred import does not dodge it — the error is reported
at ``interpreter_hub.py``, where no line-level ignore can reach.

``core.concepts.concept_factory`` and ``core.concepts.structure_generation.generator`` — the
**materialization write side**, which generates structure classes and registers them at library-load
time — also import from here, but by convention rather than necessity: both are outside
``runtime_hub``'s closure and pyright accepts the public accessor in either. Historically the binding
case was ``core.concepts.concept`` itself, which *is* in the closure (``runtime_hub`` ->
``cogt.llm.llm_worker_abstract`` -> ``system.telemetry.otel_factory`` -> ``core.pipes.pipe_output``
-> ``core.stuffs.stuff`` -> ``core.concepts.concept``) and no longer reads any registry at all.

The concept **read** side belongs behind the provider seam, not here: resolving a concept's declared
``structure_class_name`` into a class goes through a ``ConceptProviderAbstract`` implementation
(``ConceptLibrary.get_structure_class``), which is the only place that applies the ``StuffContent``
bound and raises ``ConceptStructureClassNotFoundError``. ``pipe_abstract`` above is the one sanctioned
exception, and it deliberately uses the *lenient* ``get_class`` — no bound, ``None`` rather than a
raise — because the schema it produces is optional decoration on a graph-registry entry. ``Concept``
itself reads no registry at all, pinned by
``tests/unit/pipelex/core/concepts/test_concept_registry_boundary.py``.

Note what that seam does **not** yet buy. `ConceptLibrary.get_structure_class` calls
``get_class_registry()``, so the class is resolved against whichever registry the *current async
context* selects, not against one the provider carries — a `ConceptLibrary` holds no registry of its
own (the per-library `ClassRegistry` lives on `Library`). Today the two cannot disagree: the
interpreter hub resolves both the current library and the scoped registry from the same
``_library_id`` ContextVar, and the one place that installs a per-library registry sets it and the
ContextVar on the same library in adjacent statements. Scoping resolution to the provider's own
library is therefore a one-place change if it is ever needed; see
``wip/inputs/provider-scoped-class-resolution.md`` for the trip-wires that would make it needed.

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
