import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager
from rich.console import Console

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import (
    ContentGeneratorProtocol,
)
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.inference_manager_protocol import InferenceManagerProtocol
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import Domain
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.domain.domain_library_abstract import DomainLibraryAbstract
from pipelex.libraries.library import Library
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.pipe.pipe_library_abstract import PipeLibraryAbstract
from pipelex.observer.observer_protocol import ObserverProtocol
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.plugins.sdk_client_manager import SdkClientManager
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.console_target import ConsoleTarget
from pipelex.system.environment import PIPELEXPATH_ENV_KEY, get_pipelexpath_dirs
from pipelex.system.registries.func_registry import FuncRegistry
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.file_utils import reject_bare_str_or_path
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

if TYPE_CHECKING:
    # Deferred import: avoid pulling heavy SDK at module-load time
    from opentelemetry.trace import Tracer as OTelTracer

    from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
    from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
    from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
    from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry
    from pipelex.plugins.model_lister_registry import ModelListerRegistry
    from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
    from pipelex.tracing.event_log_protocol import EventLogProtocol


class PipelexHub:
    """PipelexHub serves as a central dependency manager to break cyclic imports between components.
    It provides access to core providers and factories through a singleton instance,
    allowing components to retrieve dependencies based on protocols without direct imports that could create cycles.
    """

    _instance: ClassVar[Optional["PipelexHub"]] = None

    def __init__(self):
        # tools
        self._config: ConfigRoot | None = None
        self._console: Console | None = None
        self._secrets_provider: SecretsProviderAbstract | None = None
        self._class_registry: ClassRegistryAbstract | None = None
        self._storage_provider: StorageProviderAbstract | None = None
        self._telemetry_manager: TelemetryManagerAbstract | None = None
        self._func_registry: FuncRegistry | None = None
        # cogt
        self._models_manager: ModelManagerAbstract | None = None
        self._sdk_client_manager: SdkClientManager | None = None
        self._inference_backend_registry: InferenceBackendRegistry | None = None
        self._model_lister_registry: ModelListerRegistry | None = None
        self._orchestrator_registry: OrchestratorRegistry | None = None
        self._bundle_validator_registry: BundleValidatorRegistry | None = None
        self._inference_manager: InferenceManagerProtocol
        self._report_delegate: ReportingProtocol
        self._content_generator: ContentGeneratorProtocol | None = None
        # Keyless boot (``Pipelex.make(needs_inference=False)``) forces every run to DRY (eng
        # review D4): the backend still picks inline vs in-workflow on its own; the leaf mocks.
        # Consumed by ``PipeRunParamsFactory.make_run_params`` (the single writer of run_mode).
        self._is_dry_run_forced: bool = False

        # pipelex
        self._library_manager: LibraryManagerAbstract | None = None
        self._default_library_dirs: list[Path] | None = None
        self._domain_library: DomainLibraryAbstract | None = None
        self._concept_library: ConceptLibraryAbstract | None = None
        self._pipe_library: PipeLibraryAbstract | None = None
        self._pipe_router: PipeRouterProtocol | None = None
        self._pipe_run: PipeRunProtocol | None = None

        # pipeline
        self._pipeline_manager: PipelineManagerAbstract | None = None
        self._observer: ObserverProtocol | None = None

    ############################################################
    # Class methods for singleton management
    ############################################################

    @classmethod
    def get_optional_instance(cls) -> "PipelexHub | None":
        return cls._instance

    @classmethod
    def get_instance(cls) -> "PipelexHub":
        if cls._instance is None:
            msg = "PipelexHub is not initialized"
            raise RuntimeError(msg)
        return cls._instance

    @classmethod
    def set_instance(cls, pipelex_hub: "PipelexHub") -> None:
        cls._instance = pipelex_hub

    ############################################################
    # Setters
    ############################################################

    # tools

    def setup_config(self, config_cls: type[ConfigRoot], *, config_overrides: dict[str, Any] | None = None, config_dir: Path | None = None):
        """Set the global configuration instance.

        Args:
            config_cls: The config root class to validate against.
            config_overrides: Optional dict deep-merged on top of all TOML layers
                as the highest-priority override. Useful for tests that need
                specific config without editing TOML files.
            config_dir: Optional explicit config dir. When provided, project/global
                layering is bypassed and only this directory is read. Used by the
                doctor ``--global`` path so the hub reflects exactly the directory
                being reported on.
        """
        config_dict = config_manager.load_config(extra_overrides=config_overrides, config_dir=config_dir)
        self.set_config(config=config_cls.model_validate(config_dict))

    def set_config(self, config: ConfigRoot):
        if self._config is not None:
            log.warning("set_config() got called but it has already been set")
            return
        self._config = config

    def reset_config(self) -> None:
        """Reset the global configuration instance and the config manager."""
        self._config = None
        log.reset()

    def set_console_print_target(self, target: ConsoleTarget):
        match target:
            case ConsoleTarget.STDOUT:
                self._console = Console(file=sys.stdout)
            case ConsoleTarget.STDERR:
                self._console = Console(file=sys.stderr)
            case _:
                msg = f"Invalid console target: {target}"
                raise ValueError(msg)

    def set_console(self, console: Console):
        self._console = console

    def set_secrets_provider(self, secrets_provider: SecretsProviderAbstract):
        self._secrets_provider = secrets_provider

    def set_storage_provider(self, storage_provider: StorageProviderAbstract | None):
        self._storage_provider = storage_provider

    def set_class_registry(self, class_registry: ClassRegistryAbstract):
        self._class_registry = class_registry

    def set_telemetry_manager(self, telemetry_manager: TelemetryManagerAbstract):
        self._telemetry_manager = telemetry_manager

    # cogt

    def set_models_manager(self, models_manager: ModelManagerAbstract):
        self._models_manager = models_manager

    def set_sdk_client_manager(self, sdk_client_manager: SdkClientManager):
        self._sdk_client_manager = sdk_client_manager

    def set_inference_backend_registry(self, inference_backend_registry: "InferenceBackendRegistry"):
        self._inference_backend_registry = inference_backend_registry

    def set_model_lister_registry(self, model_lister_registry: "ModelListerRegistry"):
        self._model_lister_registry = model_lister_registry

    def set_orchestrator_registry(self, orchestrator_registry: "OrchestratorRegistry"):
        self._orchestrator_registry = orchestrator_registry

    def set_bundle_validator_registry(self, bundle_validator_registry: "BundleValidatorRegistry"):
        self._bundle_validator_registry = bundle_validator_registry

    def set_inference_manager(self, inference_manager: InferenceManagerProtocol):
        self._inference_manager = inference_manager

    def set_report_delegate(self, reporting_delegate: ReportingProtocol):
        self._report_delegate = reporting_delegate

    def set_content_generator(self, content_generator: ContentGeneratorProtocol):
        self._content_generator = content_generator

    def set_dry_run_forced(self, is_forced: bool) -> None:
        self._is_dry_run_forced = is_forced

    def is_dry_run_forced(self) -> bool:
        return self._is_dry_run_forced

    # pipelex

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

    def set_pipeline_manager(self, pipeline_manager: PipelineManagerAbstract):
        self._pipeline_manager = pipeline_manager

    def set_observer(self, observer: ObserverProtocol):
        self._observer = observer

    ############################################################
    # Getters
    ############################################################

    # tools

    def get_required_config(self) -> ConfigRoot:
        """Get the current configuration instance as an instance of a particular subclass of ConfigRoot. This should be used only from pipelex.tools.
            when getting the config from other projects, use their own project.get_config() method to get the Config
            with the proper subclass which is required for proper type checking.

        Returns:
            Config: The current configuration instance.

        Raises:
            RuntimeError: If the configuration has not been set.

        """
        if self._config is None:
            msg = "Config instance is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._config

    def get_optional_config(self) -> ConfigRoot | None:
        """Get the current configuration if it has been set, otherwise None.

        Non-raising counterpart to ``get_required_config``. Used by callers that must
        run before/around bootstrap (e.g. ``report_validation_error`` invoked from the
        doctor's setup helper when ``setup_config`` itself failed).
        """
        return self._config

    def get_console(self) -> Console:
        if self._console:
            return self._console
        else:
            return Console(stderr=True)

    def get_required_secrets_provider(self) -> SecretsProviderAbstract:
        if self._secrets_provider is None:
            msg = "Secrets provider is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._secrets_provider

    def get_required_class_registry(self) -> ClassRegistryAbstract:
        if self._class_registry is None:
            msg = "ClassRegistry is not initialized"
            raise RuntimeError(msg)
        return self._class_registry

    def get_storage_provider(self) -> StorageProviderAbstract:
        if self._storage_provider is None:
            msg = "StorageProvider is not initialized"
            raise RuntimeError(msg)
        return self._storage_provider

    def get_telemetry_manager(self) -> TelemetryManagerAbstract:
        if self._telemetry_manager is None:
            msg = "TelemetryManager is not initialized"
            raise RuntimeError(msg)
        return self._telemetry_manager

    # cogt

    def get_required_models_manager(self) -> ModelManagerAbstract:
        if self._models_manager is None:
            msg = "ModelsManager is not initialized"
            raise RuntimeError(msg)
        return self._models_manager

    def get_sdk_client_manager(self) -> SdkClientManager:
        if self._sdk_client_manager is None:
            msg = "SdkClientManager is not initialized"
            raise RuntimeError(msg)
        return self._sdk_client_manager

    def get_inference_backend_registry(self) -> "InferenceBackendRegistry":
        if self._inference_backend_registry is None:
            msg = "InferenceBackendRegistry is not initialized"
            raise RuntimeError(msg)
        return self._inference_backend_registry

    def get_model_lister_registry(self) -> "ModelListerRegistry":
        if self._model_lister_registry is None:
            msg = "ModelListerRegistry is not initialized"
            raise RuntimeError(msg)
        return self._model_lister_registry

    def get_orchestrator_registry(self) -> "OrchestratorRegistry":
        if self._orchestrator_registry is None:
            msg = "OrchestratorRegistry is not initialized"
            raise RuntimeError(msg)
        return self._orchestrator_registry

    def get_bundle_validator_registry(self) -> "BundleValidatorRegistry":
        if self._bundle_validator_registry is None:
            msg = "BundleValidatorRegistry is not initialized"
            raise RuntimeError(msg)
        return self._bundle_validator_registry

    def get_inference_manager(self) -> InferenceManagerProtocol:
        return self._inference_manager

    def get_report_delegate(self) -> ReportingProtocol:
        return self._report_delegate

    def get_required_content_generator(self) -> ContentGeneratorProtocol:
        if self._content_generator is None:
            msg = "ContentGenerator is not initialized"
            raise RuntimeError(msg)
        return self._content_generator

    # pipelex

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

    def get_required_pipeline_manager(self) -> PipelineManagerAbstract:
        if self._pipeline_manager is None:
            msg = "PipelineManager is not initialized"
            raise RuntimeError(msg)
        return self._pipeline_manager

    def get_library_manager(self) -> LibraryManagerAbstract:
        if self._library_manager is None:
            msg = "LibraryManager is not initialized"
            raise RuntimeError(msg)
        return self._library_manager

    def set_library_manager(self, library_manager: LibraryManagerAbstract):
        self._library_manager = library_manager

    def set_default_library_dirs(self, library_dirs: list[Path] | None) -> None:
        self._default_library_dirs = library_dirs

    def get_default_library_dirs(self) -> list[Path] | None:
        return self._default_library_dirs

    def get_library(self) -> Library:
        if self._library_manager is not None:
            return self._library_manager.get_current_library()
        msg = "Library is not initialized"
        raise RuntimeError(msg)

    def get_func_registry(self) -> FuncRegistry:
        if self._func_registry is None:
            msg = "FuncRegistry is not initialized"
            raise RuntimeError(msg)
        return self._func_registry

    def set_func_registry(self, func_registry: FuncRegistry):
        self._func_registry = func_registry


# Shorthand functions for accessing the singleton


def get_pipelex_hub() -> PipelexHub:
    return PipelexHub.get_instance()


def set_pipelex_hub(pipelex_hub: PipelexHub):
    PipelexHub.set_instance(pipelex_hub)


# root convenience functions

# tools


def get_required_config() -> ConfigRoot:
    return get_pipelex_hub().get_required_config()


def get_secrets_provider() -> SecretsProviderAbstract:
    return get_pipelex_hub().get_required_secrets_provider()


def get_storage_provider() -> StorageProviderAbstract:
    return get_pipelex_hub().get_storage_provider()


def get_class_registry() -> ClassRegistryAbstract:
    """Return the active class registry, respecting per-workflow library scoping.

    When a library_id is set in the current async context (e.g. inside a Temporal workflow),
    returns the library's scoped ClassRegistry. Otherwise, returns the global registry.
    """
    library_id = _library_id.get()
    if library_id is not None:
        registry = get_library_manager().get_library_class_registry(library_id)
        if registry is not None:
            return registry
    return KajsonManager.get_class_registry()


def get_func_registry() -> FuncRegistry:
    return get_pipelex_hub().get_func_registry()


def get_telemetry_manager() -> TelemetryManagerAbstract:
    return get_pipelex_hub().get_telemetry_manager()


def get_otel_tracer() -> "OTelTracer | None":
    return get_telemetry_manager().get_otel_tracer()


# cogt


def get_models_manager() -> ModelManagerAbstract:
    return get_pipelex_hub().get_required_models_manager()


def get_model_deck() -> ModelDeck:
    return get_models_manager().get_model_deck()


def get_sdk_client_manager() -> SdkClientManager:
    return get_pipelex_hub().get_sdk_client_manager()


def get_inference_backend_registry() -> "InferenceBackendRegistry":
    return get_pipelex_hub().get_inference_backend_registry()


def get_model_lister_registry() -> "ModelListerRegistry":
    return get_pipelex_hub().get_model_lister_registry()


def get_orchestrator_registry() -> "OrchestratorRegistry":
    return get_pipelex_hub().get_orchestrator_registry()


def get_bundle_validator_registry() -> "BundleValidatorRegistry":
    return get_pipelex_hub().get_bundle_validator_registry()


def get_inference_manager() -> InferenceManagerProtocol:
    return get_pipelex_hub().get_inference_manager()


def get_llm_worker(
    llm_handle: str,
) -> LLMWorkerAbstract:
    return get_inference_manager().get_llm_worker(llm_handle=llm_handle)


def get_img_gen_worker(
    img_gen_handle: str,
) -> ImgGenWorkerAbstract:
    return get_inference_manager().get_img_gen_worker(img_gen_handle=img_gen_handle)


def get_extract_worker(
    extract_handle: str,
) -> ExtractWorkerAbstract:
    return get_inference_manager().get_extract_worker(extract_handle=extract_handle)


def get_report_delegate() -> ReportingProtocol:
    return get_pipelex_hub().get_report_delegate()


_content_generator_override: ContextVar[ContentGeneratorProtocol | None] = ContextVar("content_generator_override", default=None)


@contextmanager
def scoped_content_generator(content_generator: ContentGeneratorProtocol) -> Generator[None, None, None]:
    """Set ``content_generator`` as the active generator for the scope, then restore the prior value on exit.

    Inference operators (PipeLLM / PipeImgGen / PipeExtract / PipeSearch / PipeStructure) resolve
    :func:`get_content_generator`; under a Temporal-enabled hub that default is
    ``ContentGeneratorInWorkflow``, which dispatches activities. An in-process run (e.g. the
    dry-run/validation activity body) wraps itself in this scope with an inline generator so its
    leaves never dispatch — the DRY mock lives at the cogt leaf, so the inline generator's leaves
    mock without dispatching and without storage IO. ContextVar-scoped like
    :func:`scoped_pipe_router`, so concurrent runs don't cross-contaminate.
    """
    prev = _content_generator_override.get()
    _content_generator_override.set(content_generator)
    try:
        yield
    finally:
        _content_generator_override.set(prev)


def is_dry_run_forced() -> bool:
    """True when the boot was keyless (``needs_inference=False``): every run is forced to DRY (D4)."""
    return get_pipelex_hub().is_dry_run_forced()


def get_content_generator() -> ContentGeneratorProtocol:
    override = _content_generator_override.get()
    if override is not None:
        return override
    return get_pipelex_hub().get_required_content_generator()


# pipelex


def get_secret(secret_id: str) -> str:
    return get_secrets_provider().get_secret(secret_id=secret_id)


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
    return get_pipelex_hub().get_default_library_dirs()


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

    hub_defaults = get_pipelex_hub().get_default_library_dirs()
    if hub_defaults is not None:
        return hub_defaults, "instance default"

    pipelexpath_dirs = get_pipelexpath_dirs()
    if pipelexpath_dirs is not None:
        return pipelexpath_dirs, PIPELEXPATH_ENV_KEY

    return [], "none configured"


def get_required_domain(domain_code: str) -> Domain:
    return get_pipelex_hub().get_required_domain_library().get_required_domain(domain_code=domain_code)


def get_optional_domain(domain_code: str) -> Domain | None:
    return get_pipelex_hub().get_required_domain_library().get_domain(domain_code=domain_code)


def get_pipe_library() -> PipeLibraryAbstract:
    return get_pipelex_hub().get_required_pipe_library()


def get_pipes() -> list[PipeAbstract]:
    return get_pipelex_hub().get_required_pipe_library().get_pipes()


def get_required_pipe(pipe_code: str) -> PipeAbstract:
    return get_pipelex_hub().get_required_pipe_library().get_required_pipe(pipe_code=pipe_code)


def get_optional_pipe(pipe_code: str) -> PipeAbstract | None:
    return get_pipelex_hub().get_required_pipe_library().get_optional_pipe(pipe_code=pipe_code)


def get_pipe_source(pipe_code: str) -> Path | None:
    """Get the source file path for a pipe.

    Args:
        pipe_code: The pipe code to look up.

    Returns:
        Path to the .mthds file the pipe was loaded from, or None if unknown.
    """
    return get_pipelex_hub().get_library_manager().get_pipe_source(pipe_code=pipe_code)


def get_concept_library() -> ConceptLibraryAbstract:
    return get_pipelex_hub().get_library().concept_library


def get_required_concept(concept_ref: str) -> Concept:
    return get_pipelex_hub().get_library().concept_library.get_required_concept(concept_ref=concept_ref)


_current_pipe_router: ContextVar["PipeRouterProtocol | None"] = ContextVar("current_pipe_router", default=None)


def set_pipe_router(pipe_router: "PipeRouterProtocol") -> None:
    """Override the active pipe router for the current async context.

    Used by host runtimes that want controllers to dispatch sub-pipes
    through their own router (e.g. Mistral-native mode swaps in a router
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
    because the external ``pipelex-mistralai-workflows`` plugin depends on it.
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
    return get_pipelex_hub().get_required_pipe_router()


_event_log_override: ContextVar["EventLogProtocol | None"] = ContextVar("event_log_override", default=None)


@contextmanager
def scoped_event_log(event_log: "EventLogProtocol") -> Generator[None, None, None]:
    """Pin ``event_log`` as the trace-event transport for the scope, then restore the prior value on exit.

    Both the write side (tracer emission, set up in ``pipeline_run_setup``) and the read
    side (``tracing_assembly.assemble_tracing``) prefer this override over building a new
    backend via ``make_event_log``, so emit and assemble share the SAME instance — which
    is what makes a plain in-memory event log usable for graph assembly (no external
    store bridges the two sides). A set override implies tracing-enabled: it is honored
    even when ``tracing_config.is_enabled`` is False.

    Lifecycle: the machinery never calls ``cleanup`` on the instance and the read side does
    not ``close`` it — but the write-side tracer DOES call ``close()`` on its event log at
    teardown (``GraphTracer._reset``), which happens BEFORE the read side assembles. A scoped
    event log's ``close()`` must therefore be safe to call mid-lifecycle — idempotent or a
    no-op, as ``InMemoryEventLog``'s is. Scoping a backend whose ``close()`` releases a real
    resource (NDJSON file handle, DynamoDB client) would break its own assembly read. Mirrors
    :func:`scoped_pipe_router`.
    """
    prev = _event_log_override.get()
    _event_log_override.set(event_log)
    try:
        yield
    finally:
        _event_log_override.set(prev)


def get_event_log_override() -> "EventLogProtocol | None":
    """Return the contextvar-scoped event-log override set by :func:`scoped_event_log`, or None."""
    return _event_log_override.get()


def get_pipe_run() -> "PipeRunProtocol":
    return get_pipelex_hub().get_required_pipe_run()


def get_pipeline_manager() -> PipelineManagerAbstract:
    return get_pipelex_hub().get_required_pipeline_manager()


def get_pipeline(pipeline_run_id: str) -> Pipeline:
    return get_pipeline_manager().get_pipeline(pipeline_run_id=pipeline_run_id)


def get_library_manager() -> LibraryManagerAbstract:
    return get_pipelex_hub().get_library_manager()


def get_library() -> Library:
    return get_pipelex_hub().get_library()


def get_native_concept(native_concept: NativeConceptCode) -> Concept:
    return get_pipelex_hub().get_required_concept_library().get_native_concept(native_concept=native_concept)


def get_console() -> Console:
    pipelex_hub = PipelexHub.get_optional_instance()
    if pipelex_hub:
        return pipelex_hub.get_console()
    else:
        return Console(stderr=True)
