import sys
from collections.abc import Sequence
from contextvars import ContextVar
from pathlib import Path
from typing import ClassVar, Optional

from kajson.class_registry_abstract import ClassRegistryAbstract
from opentelemetry.trace import Tracer as OTelTracer
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
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.plugins.plugin_manager import PluginManager
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.console_target import ConsoleTarget
from pipelex.system.environment import PIPELEXPATH_ENV_KEY, get_pipelexpath_dirs
from pipelex.system.telemetry.telemetry_manager import TelemetryManagerAbstract
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


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

        # cogt
        self._models_manager: ModelManagerAbstract | None = None
        self._plugin_manager: PluginManager | None = None
        self._inference_manager: InferenceManagerProtocol
        self._report_delegate: ReportingProtocol
        self._content_generator: ContentGeneratorProtocol | None = None

        # pipelex
        self._library_manager: LibraryManagerAbstract | None = None
        self._default_library_dirs: list[Path] | None = None
        self._domain_library: DomainLibraryAbstract | None = None
        self._concept_library: ConceptLibraryAbstract | None = None
        self._pipe_library: PipeLibraryAbstract | None = None
        self._pipe_router: PipeRouterProtocol | None = None

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

    def setup_config(self, config_cls: type[ConfigRoot]):
        """Set the global configuration instance.

        # Args:
        #     config (Config): The configuration instance to set.
        """
        config_dict = config_manager.load_config()
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

    def set_plugin_manager(self, plugin_manager: PluginManager):
        self._plugin_manager = plugin_manager

    def set_inference_manager(self, inference_manager: InferenceManagerProtocol):
        self._inference_manager = inference_manager

    def set_report_delegate(self, reporting_delegate: ReportingProtocol):
        self._report_delegate = reporting_delegate

    def set_content_generator(self, content_generator: ContentGeneratorProtocol):
        self._content_generator = content_generator

    # pipelex

    def set_domain_library(self, domain_library: DomainLibraryAbstract):
        self._domain_library = domain_library

    def set_concept_library(self, concept_library: ConceptLibraryAbstract):
        self._concept_library = concept_library

    def set_pipe_library(self, pipe_library: PipeLibraryAbstract):
        self._pipe_library = pipe_library

    def set_pipe_router(self, pipe_router: PipeRouterProtocol):
        self._pipe_router = pipe_router

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

    def get_plugin_manager(self) -> PluginManager:
        if self._plugin_manager is None:
            msg = "PluginManager2 is not initialized"
            raise RuntimeError(msg)
        return self._plugin_manager

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

    def get_required_pipe_router(self) -> PipeRouterProtocol:
        if self._pipe_router is None:
            msg = "PipeRouter is not initialized"
            raise RuntimeError(msg)
        return self._pipe_router

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
    return get_pipelex_hub().get_required_class_registry()


def get_telemetry_manager() -> TelemetryManagerAbstract:
    return get_pipelex_hub().get_telemetry_manager()


def get_otel_tracer() -> OTelTracer | None:
    return get_telemetry_manager().get_otel_tracer()


# cogt


def get_models_manager() -> ModelManagerAbstract:
    return get_pipelex_hub().get_required_models_manager()


def get_model_deck() -> ModelDeck:
    return get_models_manager().get_model_deck()


def get_plugin_manager() -> PluginManager:
    return get_pipelex_hub().get_plugin_manager()


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


def get_content_generator() -> ContentGeneratorProtocol:
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


def teardown_current_library() -> None:
    """Teardown the library_id for the current async context."""
    _library_id.set(None)


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
        Path to the .plx file the pipe was loaded from, or None if unknown.
    """
    return get_pipelex_hub().get_library_manager().get_pipe_source(pipe_code=pipe_code)


def get_concept_library() -> ConceptLibraryAbstract:
    return get_pipelex_hub().get_library().concept_library


def get_required_concept(concept_ref: str) -> Concept:
    return get_pipelex_hub().get_library().concept_library.get_required_concept(concept_ref=concept_ref)


def get_pipe_router() -> PipeRouterProtocol:
    return get_pipelex_hub().get_required_pipe_router()


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
