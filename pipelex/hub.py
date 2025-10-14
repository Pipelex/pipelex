from typing import ClassVar, Optional

from kajson.class_registry_abstract import ClassRegistryAbstract

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
from pipelex.core.concepts.concept_library_abstract import ConceptLibraryAbstract
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_library_abstract import DomainLibraryAbstract
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_library_abstract import PipeLibraryAbstract
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.observer.observer_protocol import ObserverProtocol
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.activity.activity_manager_protocol import ActivityManagerProtocol
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.pipeline.track.pipeline_tracker_protocol import PipelineTrackerProtocol
from pipelex.plugins.plugin_manager import PluginManager
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
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
        self._secrets_provider: SecretsProviderAbstract | None = None
        self._class_registry: ClassRegistryAbstract | None = None
        self._storage_provider: StorageProviderAbstract | None = None
        # cogt
        self._models_manager: ModelManagerAbstract | None = None
        self._plugin_manager: PluginManager | None = None
        self._inference_manager: InferenceManagerProtocol
        self._report_delegate: ReportingProtocol
        self._content_generator: ContentGeneratorProtocol | None = None

        # pipelex
        self._domain_library: DomainLibraryAbstract | None = None
        self._concept_library: ConceptLibraryAbstract | None = None
        self._pipe_library: PipeLibraryAbstract | None = None
        self._pipe_router: PipeRouterProtocol | None = None
        self._library_manager: LibraryManagerAbstract | None = None

        # pipeline
        self._pipeline_tracker: PipelineTrackerProtocol | None = None
        self._pipeline_manager: PipelineManagerAbstract | None = None
        self._activity_manager: ActivityManagerProtocol | None = None
        self._observer_provider: ObserverProtocol | None = None

    ############################################################
    # Class methods for singleton management
    ############################################################

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

    def setup_config(self, config_cls: type[ConfigRoot], specific_config_path: str | None = None):
        """Set the global configuration instance.

        # Args:
        #     config (Config): The configuration instance to set.
        """
        config = config_manager.load_config(specific_config_path)
        config["project_name"] = config_manager.get_project_name()
        self.set_config(config=config_cls.model_validate(config))

    def set_config(self, config: ConfigRoot):
        if self._config is not None:
            log.warning(f"set_config() got called but {self._config.project_name} config has already been set")
            return
        self._config = config

    def reset_config(self) -> None:
        """Reset the global configuration instance and the config manager."""
        self._config = None
        log.reset()

    def set_secrets_provider(self, secrets_provider: SecretsProviderAbstract):
        self._secrets_provider = secrets_provider

    def set_storage_provider(self, storage_provider: StorageProviderAbstract | None):
        self._storage_provider = storage_provider

    def set_class_registry(self, class_registry: ClassRegistryAbstract):
        self._class_registry = class_registry

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

    def set_pipeline_tracker(self, pipeline_tracker: PipelineTrackerProtocol):
        self._pipeline_tracker = pipeline_tracker

    def set_pipeline_manager(self, pipeline_manager: PipelineManagerAbstract):
        self._pipeline_manager = pipeline_manager

    def set_activity_manager(self, activity_manager: ActivityManagerProtocol):
        self._activity_manager = activity_manager

    def set_library_manager(self, library_manager: LibraryManagerAbstract):
        self._library_manager = library_manager

    def set_observer_provider(self, observer_provider: ObserverProtocol):
        self._observer_provider = observer_provider

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
        if self._domain_library is None:
            msg = "DomainLibrary is not initialized"
            raise RuntimeError(msg)
        return self._domain_library

    def get_required_concept_library(self) -> ConceptLibraryAbstract:
        if self._concept_library is None:
            msg = "ConceptLibrary is not initialized"
            raise RuntimeError(msg)
        return self._concept_library

    def get_required_pipe_library(self) -> PipeLibraryAbstract:
        if self._pipe_library is None:
            msg = "PipeLibrary is not initialized"
            raise RuntimeError(msg)
        return self._pipe_library

    def get_required_pipe_router(self) -> PipeRouterProtocol:
        if self._pipe_router is None:
            msg = "PipeRouter is not initialized"
            raise RuntimeError(msg)
        return self._pipe_router

    def get_pipeline_tracker(self) -> PipelineTrackerProtocol:
        if self._pipeline_tracker is None:
            msg = "PipelineTracker is not initialized"
            raise RuntimeError(msg)
        return self._pipeline_tracker

    def get_required_pipeline_manager(self) -> PipelineManagerAbstract:
        if self._pipeline_manager is None:
            msg = "PipelineManager is not initialized"
            raise RuntimeError(msg)
        return self._pipeline_manager

    def get_activity_manager(self) -> ActivityManagerProtocol:
        if self._activity_manager is None:
            msg = "Activity manager is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._activity_manager

    def get_required_library_manager(self) -> LibraryManagerAbstract:
        if self._library_manager is None:
            msg = "Library manager is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._library_manager

    def get_observer_provider(self) -> ObserverProtocol:
        if self._observer_provider is None:
            msg = "Observer is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._observer_provider


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


def get_required_domain(domain: str) -> Domain:
    return get_pipelex_hub().get_required_domain_library().get_required_domain(domain=domain)


def get_optional_domain(domain: str) -> Domain | None:
    return get_pipelex_hub().get_required_domain_library().get_domain(domain=domain)


def get_pipe_library() -> PipeLibraryAbstract:
    return get_pipelex_hub().get_required_pipe_library()


def get_pipes() -> list[PipeAbstract]:
    return get_pipelex_hub().get_required_pipe_library().get_pipes()


def get_required_pipe(pipe_code: str) -> PipeAbstract:
    return get_pipelex_hub().get_required_pipe_library().get_required_pipe(pipe_code=pipe_code)


def get_optional_pipe(pipe_code: str) -> PipeAbstract | None:
    return get_pipelex_hub().get_required_pipe_library().get_optional_pipe(pipe_code=pipe_code)


def get_concept_library() -> ConceptLibraryAbstract:
    return get_pipelex_hub().get_required_concept_library()


def get_required_concept(concept_string: str) -> Concept:
    return get_pipelex_hub().get_required_concept_library().get_required_concept(concept_string=concept_string)


def get_pipe_router() -> PipeRouterProtocol:
    return get_pipelex_hub().get_required_pipe_router()


def get_pipeline_tracker() -> PipelineTrackerProtocol:
    return get_pipelex_hub().get_pipeline_tracker()


def get_pipeline_manager() -> PipelineManagerAbstract:
    return get_pipelex_hub().get_required_pipeline_manager()


def get_activity_manager() -> ActivityManagerProtocol:
    return get_pipelex_hub().get_activity_manager()


def get_pipeline(pipeline_run_id: str) -> Pipeline:
    return get_pipeline_manager().get_pipeline(pipeline_run_id=pipeline_run_id)


def get_library_manager() -> LibraryManagerAbstract:
    return get_pipelex_hub().get_required_library_manager()


def get_observer_provider() -> ObserverProtocol:
    return get_pipelex_hub().get_observer_provider()


def get_native_concept(native_concept: NativeConceptCode) -> Concept:
    return get_pipelex_hub().get_required_concept_library().get_native_concept(native_concept=native_concept)
