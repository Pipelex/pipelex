"""The interpreter layer's dependency hub: library-scoped method machinery.

``InterpreterHub`` brokers everything tied to the *loaded method* rather than to the process: the
library manager and the domain/concept/pipe libraries, the current-library contextvar family, the
pipe router, the pipe runner, the pipeline manager, and the PipeFunc executor. That is the half
that reads the program and executes it — hence *interpreter*.

**The one rule:** this module MAY import ``runtime_hub``; ``runtime_hub`` must never import this
one. As it happens the arrow is currently unused — the only kernel-layer thing this module needs
is the class-registry scoping slot, which lives below both hubs in
``system.registries.class_registry_access``. See ``docs/contribute/hub-layering.md``.
"""

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional

from kajson.class_registry_abstract import ClassRegistryAbstract

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import Domain
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.domain.domain_library_abstract import DomainLibraryAbstract
from pipelex.libraries.library import Library
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.pipe.pipe_library_abstract import PipeLibraryAbstract
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutorProtocol
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.system.environment import PIPELEXPATH_ENV_KEY, get_pipelexpath_dirs
from pipelex.system.registries.class_registry_access import class_registry_scoping
from pipelex.tools.misc.file_utils import reject_bare_str_or_path

if TYPE_CHECKING:
    from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
    from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
    from pipelex.plugins.pipe_func_executor_registry import PipeFuncExecutorRegistry


class InterpreterHub:
    """Central dependency manager for the method-interpretation layer.

    Holds the libraries of the currently loaded method plus the machinery that runs it. Its
    lifecycle is library-scoped — the ``_library_id`` contextvar below selects which library is
    current — whereas ``pipelex.runtime_hub.RuntimeHub`` is process-scoped.
    """

    _instance: ClassVar[Optional["InterpreterHub"]] = None

    def __init__(self):
        # libraries
        self._library_manager: LibraryManagerAbstract | None = None
        self._default_library_dirs: list[Path] | None = None
        self._domain_library: DomainLibraryAbstract | None = None
        self._concept_library: ConceptLibraryAbstract | None = None
        self._pipe_library: PipeLibraryAbstract | None = None
        # run
        self._pipe_router: PipeRouterProtocol | None = None
        self._pipe_run: PipeRunProtocol | None = None
        self._pipe_func_executor: PipeFuncExecutorProtocol | None = None
        self._pipe_func_executor_registry: PipeFuncExecutorRegistry | None = None
        # pipeline
        self._pipeline_manager: PipelineManagerAbstract | None = None

    ############################################################
    # Class methods for singleton management
    ############################################################

    @classmethod
    def get_optional_instance(cls) -> "InterpreterHub | None":
        return cls._instance

    @classmethod
    def get_instance(cls) -> "InterpreterHub":
        if cls._instance is None:
            msg = "InterpreterHub is not initialized"
            raise RuntimeError(msg)
        return cls._instance

    @classmethod
    def set_instance(cls, interpreter_hub: "InterpreterHub") -> None:
        cls._instance = interpreter_hub

    ############################################################
    # Setters
    ############################################################

    def set_library_manager(self, library_manager: LibraryManagerAbstract):
        self._library_manager = library_manager

    def set_default_library_dirs(self, library_dirs: list[Path] | None) -> None:
        self._default_library_dirs = library_dirs

    def set_domain_library(self, domain_library: DomainLibraryAbstract):
        self._domain_library = domain_library

    def set_concept_library(self, concept_library: ConceptLibraryAbstract):
        self._concept_library = concept_library

    def set_pipe_library(self, pipe_library: PipeLibraryAbstract):
        self._pipe_library = pipe_library

    def set_pipe_router(self, pipe_router: "PipeRouterProtocol"):
        self._pipe_router = pipe_router

    def set_pipe_run(self, pipe_run: "PipeRunProtocol") -> None:
        self._pipe_run = pipe_run

    def set_pipe_func_executor(self, pipe_func_executor: PipeFuncExecutorProtocol):
        self._pipe_func_executor = pipe_func_executor

    def set_pipe_func_executor_registry(self, pipe_func_executor_registry: "PipeFuncExecutorRegistry"):
        self._pipe_func_executor_registry = pipe_func_executor_registry

    def set_pipeline_manager(self, pipeline_manager: PipelineManagerAbstract):
        self._pipeline_manager = pipeline_manager

    ############################################################
    # Getters
    ############################################################

    def get_library_manager(self) -> LibraryManagerAbstract:
        if self._library_manager is None:
            msg = "LibraryManager is not initialized"
            raise RuntimeError(msg)
        return self._library_manager

    def get_default_library_dirs(self) -> list[Path] | None:
        return self._default_library_dirs

    def get_library(self) -> Library:
        if self._library_manager is not None:
            return self._library_manager.get_current_library()
        msg = "Library is not initialized"
        raise RuntimeError(msg)

    def get_required_domain_library(self) -> DomainLibraryAbstract:
        if self._library_manager is not None:
            return self._library_manager.get_current_library().domain_library
        if self._domain_library is None:
            msg = "DomainLibrary is not initialized"
            raise RuntimeError(msg)
        return self._domain_library

    def get_required_concept_library(self) -> ConceptLibraryAbstract:
        if self._library_manager is not None:
            return self._library_manager.get_current_library().concept_library
        if self._concept_library is None:
            msg = "ConceptLibrary is not initialized"
            raise RuntimeError(msg)
        return self._concept_library

    def get_required_pipe_library(self) -> PipeLibraryAbstract:
        if self._library_manager is not None:
            return self._library_manager.get_current_library().pipe_library
        if self._pipe_library is None:
            msg = "PipeLibrary is not initialized"
            raise RuntimeError(msg)
        return self._pipe_library

    def get_required_pipe_router(self) -> "PipeRouterProtocol":
        if self._pipe_router is None:
            msg = "PipeRouter is not initialized"
            raise RuntimeError(msg)
        return self._pipe_router

    def get_required_pipe_run(self) -> "PipeRunProtocol":
        if self._pipe_run is None:
            msg = "PipeRun is not initialized"
            raise RuntimeError(msg)
        return self._pipe_run

    def get_required_pipe_func_executor(self) -> PipeFuncExecutorProtocol:
        if self._pipe_func_executor is None:
            msg = "PipeFuncExecutor is not initialized"
            raise RuntimeError(msg)
        return self._pipe_func_executor

    def get_pipe_func_executor_registry(self) -> "PipeFuncExecutorRegistry":
        if self._pipe_func_executor_registry is None:
            msg = "PipeFuncExecutorRegistry is not initialized"
            raise RuntimeError(msg)
        return self._pipe_func_executor_registry

    def get_required_pipeline_manager(self) -> PipelineManagerAbstract:
        if self._pipeline_manager is None:
            msg = "PipelineManager is not initialized"
            raise RuntimeError(msg)
        return self._pipeline_manager


# Shorthand functions for accessing the singleton


def get_interpreter_hub() -> InterpreterHub:
    return InterpreterHub.get_instance()


def set_interpreter_hub(interpreter_hub: InterpreterHub):
    """Install ``interpreter_hub`` as the process singleton, and hand the kernel layer its scoping resolver.

    Installing the resolver here rather than at an explicit boot step means library scoping is
    active exactly when an InterpreterHub exists — the invariant ``get_class_registry`` relies on, and
    one a caller cannot forget to wire. The resolver crosses downward at install time, never as an
    import from ``runtime_hub``.
    """
    InterpreterHub.set_instance(interpreter_hub)
    class_registry_scoping.install(resolver=_resolve_scoped_class_registry)


def _resolve_scoped_class_registry() -> ClassRegistryAbstract | None:
    """Resolve the current library's ClassRegistry, or None when nothing narrows the lookup.

    Returns None both when no library is pinned in the current async context and when the pinned
    library carries no registry of its own; ``get_class_registry`` then serves the process-global
    Kajson registry.
    """
    library_id = _library_id.get()
    if library_id is None:
        return None
    return get_library_manager().get_library_class_registry(library_id)


# libraries


_library_id: ContextVar[str | None] = ContextVar("library_id", default=None)


def set_current_library(library_id: str) -> None:
    """Set the library_id for the current async context."""
    _library_id.set(library_id)


def get_current_library() -> str:
    """Get the library_id from the current async context."""
    library_id = _library_id.get()
    if library_id is None:
        msg = "No current library set. Must call set_current_library() first."
        raise RuntimeError(msg)
    return library_id


def get_current_library_id_or_none() -> str | None:
    """Return the current library_id, or ``None`` if none is set."""
    return _library_id.get()


def get_default_library_dirs() -> list[Path] | None:
    return get_interpreter_hub().get_default_library_dirs()


def clear_current_library() -> None:
    """Clear the current-library binding (the ``None`` case of :func:`set_current_library`).

    Resets the ``_library_id`` ContextVar to ``None`` for the current async context. This only
    drops the *pointer* to which library is current — it does **not** free the ``Library`` object
    from the ``LibraryManager``. To release the library itself, call
    ``library_manager.teardown(library_id=...)`` (the two are distinct and a full cleanup typically
    does both).
    """
    _library_id.set(None)


@contextmanager
def scoped_current_library(library_id: str) -> Generator[None, None, None]:
    """Set ``library_id`` for the scope, then restore the prior value on exit.

    Captures the prior ``_library_id`` ContextVar value before setting the new
    one. On exit — success or exception — restores the prior value (or clears
    the var if there wasn't one). Use this whenever a function temporarily
    needs a current library for a nested operation without clobbering an
    outer caller's library_id.
    """
    prev = _library_id.get()
    _library_id.set(library_id)
    try:
        yield
    finally:
        _library_id.set(prev)


def resolve_library_dirs(library_dirs: Sequence[str | Path] | None = None) -> tuple[list[Path], str]:
    """Resolve library directories following the standard 3-tier priority.

    Resolution priority:
    1. Per-call library_dirs (explicit override)
    2. Instance-level defaults from Pipelex.make()
    3. PIPELEXPATH environment variable (fallback)

    Note: An empty list [] is a valid explicit value that disables library loading.

    Args:
        library_dirs: Optional per-call override. If provided (even if empty),
            takes precedence over instance defaults and PIPELEXPATH.

    Returns:
        A tuple of (effective_dirs, source_label) where:
        - effective_dirs: The resolved list of Path objects
        - source_label: A string describing the source for logging (e.g., "per-call")
    """
    reject_bare_str_or_path(library_dirs, param_name="library_dirs")
    if library_dirs is not None:
        return [Path(lib_dir) for lib_dir in library_dirs], "per-call"

    hub_defaults = get_interpreter_hub().get_default_library_dirs()
    if hub_defaults is not None:
        return hub_defaults, "instance default"

    pipelexpath_dirs = get_pipelexpath_dirs()
    if pipelexpath_dirs is not None:
        return pipelexpath_dirs, PIPELEXPATH_ENV_KEY

    return [], "none configured"


def get_library_manager() -> LibraryManagerAbstract:
    return get_interpreter_hub().get_library_manager()


def get_library() -> Library:
    return get_interpreter_hub().get_library()


def get_required_domain(domain_code: str) -> Domain:
    return get_interpreter_hub().get_required_domain_library().get_required_domain(domain_code=domain_code)


def get_optional_domain(domain_code: str) -> Domain | None:
    return get_interpreter_hub().get_required_domain_library().get_domain(domain_code=domain_code)


def get_pipe_library() -> PipeLibraryAbstract:
    return get_interpreter_hub().get_required_pipe_library()


def get_pipes() -> list[PipeAbstract]:
    return get_interpreter_hub().get_required_pipe_library().get_pipes()


def get_required_pipe(pipe_code: str) -> PipeAbstract:
    return get_interpreter_hub().get_required_pipe_library().get_required_pipe(pipe_code=pipe_code)


def get_optional_pipe(pipe_code: str) -> PipeAbstract | None:
    return get_interpreter_hub().get_required_pipe_library().get_optional_pipe(pipe_code=pipe_code)


def get_pipe_source(pipe_code: str) -> str | None:
    """Get the source identifier for a pipe.

    Args:
        pipe_code: The pipe code to look up.

    Returns:
        The source the pipe was loaded from — a filesystem path or a logical URI,
        preserved verbatim — or None if unknown.
    """
    return get_interpreter_hub().get_library_manager().get_pipe_source(pipe_code=pipe_code)


def get_concept_library() -> ConceptLibraryAbstract:
    return get_interpreter_hub().get_library().concept_library


def get_required_concept(concept_ref: str) -> Concept:
    return get_interpreter_hub().get_library().concept_library.get_required_concept(concept_ref=concept_ref)


def get_native_concept(native_concept: NativeConceptCode) -> Concept:
    return get_interpreter_hub().get_required_concept_library().get_native_concept(native_concept=native_concept)


# pipe router


_current_pipe_router: ContextVar["PipeRouterProtocol | None"] = ContextVar("current_pipe_router", default=None)


def set_pipe_router(pipe_router: "PipeRouterProtocol") -> None:
    """Override the active pipe router for the current async context.

    Used by host runtimes that want controllers to dispatch sub-pipes
    through their own router (e.g. Mistral Workflows mode swaps in a router
    that turns sub-pipe calls into child workflows / activities). The
    override is contextvar-scoped, so concurrent runs on the same hub
    don't leak into each other. Pass ``None`` via
    ``teardown_current_pipe_router()`` to restore the hub default.
    """
    _current_pipe_router.set(pipe_router)


def teardown_current_pipe_router() -> None:
    """Clear any contextvar-scoped router override set by ``set_pipe_router``."""
    _current_pipe_router.set(None)


@contextmanager
def scoped_pipe_router(pipe_router: "PipeRouterProtocol") -> Generator[None, None, None]:
    """Set ``pipe_router`` as the active router for the scope, then restore the prior value on exit.

    Captures the prior ``_current_pipe_router`` ContextVar value before setting
    the new one. On exit — success or exception — restores the prior override
    (or clears it if there wasn't one). Use this whenever a call needs its own
    router for the *whole* run (root pipe + nested controller sub-pipes, which
    resolve :func:`get_pipe_router`) without clobbering an outer caller's
    override. Mirrors :func:`scoped_current_library`.

    Prefer this over the raw ``set_pipe_router`` / ``teardown_current_pipe_router``
    pair internally: the raw teardown unconditionally resets the override to
    ``None`` and so does not restore an outer override. The raw pair is kept
    because our Mistral Workflows plugin depends on it.
    """
    prev = _current_pipe_router.get()
    _current_pipe_router.set(pipe_router)
    try:
        yield
    finally:
        _current_pipe_router.set(prev)


def get_pipe_router() -> "PipeRouterProtocol":
    override = _current_pipe_router.get()
    if override is not None:
        return override
    return get_interpreter_hub().get_required_pipe_router()


# pipe func


_pipe_func_executor_override: ContextVar[PipeFuncExecutorProtocol | None] = ContextVar("pipe_func_executor_override", default=None)


@contextmanager
def scoped_pipe_func_executor(pipe_func_executor: PipeFuncExecutorProtocol) -> Generator[None, None, None]:
    """Set ``pipe_func_executor`` as the active executor for the scope, then restore the prior value on exit.

    The PipeFunc counterpart of :func:`pipelex.runtime_hub.scoped_content_generator`: in a process
    whose hub default executor dispatches PipeFunc steps out-of-process (a distributed-orchestrator
    worker), this scope lets an in-process run force a specific executor — e.g. the local one, so
    its PipeFunc steps run here instead of being re-dispatched. ContextVar-scoped like
    :func:`scoped_pipe_router`, so concurrent runs never cross-contaminate.
    """
    prev = _pipe_func_executor_override.get()
    _pipe_func_executor_override.set(pipe_func_executor)
    try:
        yield
    finally:
        _pipe_func_executor_override.set(prev)


def get_pipe_func_executor() -> PipeFuncExecutorProtocol:
    override = _pipe_func_executor_override.get()
    if override is not None:
        return override
    return get_interpreter_hub().get_required_pipe_func_executor()


def get_pipe_func_executor_registry() -> "PipeFuncExecutorRegistry":
    return get_interpreter_hub().get_pipe_func_executor_registry()


# run


def get_pipe_run() -> "PipeRunProtocol":
    return get_interpreter_hub().get_required_pipe_run()


def get_pipeline_manager() -> PipelineManagerAbstract:
    return get_interpreter_hub().get_required_pipeline_manager()


def get_pipeline(pipeline_run_id: str) -> Pipeline:
    return get_pipeline_manager().get_pipeline(pipeline_run_id=pipeline_run_id)
