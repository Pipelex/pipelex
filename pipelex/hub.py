from collections import defaultdict
from typing import ClassVar, Dict, List, Optional, Type

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.inference.inference_manager_protocol import InferenceManagerProtocol
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_models.llm_deck_abstract import LLMDeckAbstract
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_model_provider_abstract import LLMModelProviderAbstract
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.cogt.plugin_manager import PluginManager
from pipelex.core.concept import Concept
from pipelex.core.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.domain import Domain
from pipelex.core.domain_provider_abstract import DomainProviderAbstract
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_provider_abstract import PipeProviderAbstract
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.activity.activity_manager_protocol import ActivityManagerProtocol
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.pipeline.track.pipeline_tracker_protocol import PipelineTrackerProtocol
from pipelex.tools.config.manager import config_manager
from pipelex.tools.config.models import ConfigRoot
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.templating.template_provider_abstract import TemplateProviderAbstract


class PipelexHub:
    """
    PipelexHub serves as a central dependency manager to break cyclic imports between components.
    It provides access to core providers and factories through a singleton instance,
    allowing components to retrieve dependencies based on protocols without direct imports that could create cycles.
    """

    _instance: ClassVar[Optional["PipelexHub"]] = None

    def __init__(self):
        # tools
        self._config: Optional[ConfigRoot] = None
        self._secrets_provider: Optional[SecretsProviderAbstract] = None
        self._template_provider: Optional[TemplateProviderAbstract] = None
        # cogt
        self._llm_models_provider: Optional[LLMModelProviderAbstract] = None
        self._llm_deck_provider: Optional[LLMDeckAbstract] = None
        self._plugin_manager: Optional[PluginManager] = None
        self._inference_manager: InferenceManagerProtocol
        self._report_delegate: InferenceReportDelegate
        self._content_generator: Optional[ContentGeneratorProtocol] = None

        # pipelex
        self._domain_provider: Optional[DomainProviderAbstract] = None
        self._concept_provider: Optional[ConceptProviderAbstract] = None
        self._pipe_provider: Optional[PipeProviderAbstract] = None
        self._pipe_router: Optional[PipeRouterProtocol] = None

        # pipeline
        self._pipeline_tracker: Optional[PipelineTrackerProtocol] = None
        self._pipeline_manager: Optional[PipelineManagerAbstract] = None
        self._activity_manager: Optional[ActivityManagerProtocol] = None

    ############################################################
    # Class methods for singleton management
    ############################################################

    @classmethod
    def get_instance(cls) -> "PipelexHub":
        if cls._instance is None:
            raise RuntimeError("PipelexHub is not initialized")
        return cls._instance

    @classmethod
    def set_instance(cls, pipelex_hub: "PipelexHub") -> None:
        cls._instance = pipelex_hub

    ############################################################
    # Setters
    ############################################################

    # tools

    def setup_config(self, config_cls: Type[ConfigRoot], specific_config_path: Optional[str] = None):
        """
        Set the global configuration instance.

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
        """
        Reset the global configuration instance and the config manager.
        """
        self._config = None
        log.reset()

    def set_secrets_provider(self, secrets_provider: SecretsProviderAbstract):
        self._secrets_provider = secrets_provider

    def set_template_provider(self, template_provider: TemplateProviderAbstract):
        self._template_provider = template_provider

    # cogt

    def set_llm_models_provider(self, llm_models_provider: LLMModelProviderAbstract):
        self._llm_models_provider = llm_models_provider

    def set_llm_deck_provider(self, llm_deck_provider: LLMDeckAbstract):
        self._llm_deck_provider = llm_deck_provider

    def set_plugin_manager(self, plugin_manager: PluginManager):
        self._plugin_manager = plugin_manager

    def set_inference_manager(self, inference_manager: InferenceManagerProtocol):
        self._inference_manager = inference_manager

    def set_report_delegate(self, report_delegate: InferenceReportDelegate):
        self._report_delegate = report_delegate

    def set_content_generator(self, content_generator: ContentGeneratorProtocol):
        self._content_generator = content_generator

    # pipelex

    def set_domain_provider(self, domain_provider: DomainProviderAbstract):
        self._domain_provider = domain_provider

    def set_concept_provider(self, concept_provider: ConceptProviderAbstract):
        self._concept_provider = concept_provider

    def set_pipe_provider(self, pipe_provider: PipeProviderAbstract):
        self._pipe_provider = pipe_provider

    def set_pipe_router(self, pipe_router: PipeRouterProtocol):
        self._pipe_router = pipe_router

    def set_pipeline_tracker(self, pipeline_tracker: PipelineTrackerProtocol):
        self._pipeline_tracker = pipeline_tracker

    def set_pipeline_manager(self, pipeline_manager: PipelineManagerAbstract):
        self._pipeline_manager = pipeline_manager

    def set_activity_manager(self, activity_manager: ActivityManagerProtocol):
        self._activity_manager = activity_manager

    ############################################################
    # Getters
    ############################################################

    # tools

    def get_required_config(self) -> ConfigRoot:
        """
        Get the current configuration instance as an instance of a particular subclass of ConfigRoot. This should be used only from pipelex.tools.
            when getting the config from other projects, use their own project.get_config() method to get the Config
            with the proper subclass which is required for proper type checking.

        Returns:
            Config: The current configuration instance.

        Raises:
            RuntimeError: If the configuration has not been set.
        """
        if self._config is None:
            raise RuntimeError("Config instance is not set. You must initialize Pipelex first.")
        return self._config

    def get_required_secrets_provider(self) -> SecretsProviderAbstract:
        if self._secrets_provider is None:
            raise RuntimeError("Secrets provider is not set. You must initialize Pipelex first.")
        return self._secrets_provider

    def get_required_template_provider(self) -> TemplateProviderAbstract:
        if self._template_provider is None:
            raise RuntimeError("Template provider is not set. You must initialize Pipelex first.")
        return self._template_provider

    # cogt

    def get_required_llm_models_provider(self) -> LLMModelProviderAbstract:
        if self._llm_models_provider is None:
            raise RuntimeError("LLMModelProvider is not initialized")
        return self._llm_models_provider

    def get_optional_llm_models_provider(self) -> Optional[LLMModelProviderAbstract]:
        return self._llm_models_provider

    def get_required_llm_deck(self) -> LLMDeckAbstract:
        if self._llm_deck_provider is None:
            raise RuntimeError("LLMDeck is not initialized")
        return self._llm_deck_provider

    def get_plugin_manager(self) -> PluginManager:
        if self._plugin_manager is None:
            raise RuntimeError("SdkManager is not initialized")
        return self._plugin_manager

    def get_inference_manager(self) -> InferenceManagerProtocol:
        return self._inference_manager

    def get_report_delegate(self) -> InferenceReportDelegate:
        return self._report_delegate

    def get_required_content_generator(self) -> ContentGeneratorProtocol:
        if self._content_generator is None:
            raise RuntimeError("ContentGenerator is not initialized")
        return self._content_generator

    # pipelex

    def get_required_domain_provider(self) -> DomainProviderAbstract:
        if self._domain_provider is None:
            raise RuntimeError("DomainProvider is not initialized")
        return self._domain_provider

    def get_optional_domain_provider(self) -> Optional[DomainProviderAbstract]:
        return self._domain_provider

    def get_required_concept_provider(self) -> ConceptProviderAbstract:
        if self._concept_provider is None:
            raise RuntimeError("ConceptProvider is not initialized")
        return self._concept_provider

    def get_optional_concept_provider(self) -> Optional[ConceptProviderAbstract]:
        return self._concept_provider

    def get_required_pipe_provider(self) -> PipeProviderAbstract:
        if self._pipe_provider is None:
            raise RuntimeError("PipeProvider is not initialized")
        return self._pipe_provider

    def get_required_pipe_router(self) -> PipeRouterProtocol:
        if self._pipe_router is None:
            raise RuntimeError("PipeRouter is not initialized")
        return self._pipe_router

    def get_pipeline_tracker(self) -> PipelineTrackerProtocol:
        if self._pipeline_tracker is None:
            raise RuntimeError("PipelineTracker is not initialized")
        return self._pipeline_tracker

    def get_required_pipeline_manager(self) -> PipelineManagerAbstract:
        if self._pipeline_manager is None:
            raise RuntimeError("PipelineManager is not initialized")
        return self._pipeline_manager

    def get_activity_manager(self) -> ActivityManagerProtocol:
        if self._activity_manager is None:
            raise RuntimeError("ActivityManager is not initialized")
        return self._activity_manager


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


def get_template_provider() -> TemplateProviderAbstract:
    return get_pipelex_hub().get_required_template_provider()


def get_template(template_name: str) -> str:
    return get_template_provider().get_template(template_name=template_name)


# cogt


def get_llm_models_provider() -> LLMModelProviderAbstract:
    return get_pipelex_hub().get_required_llm_models_provider()


def get_llm_deck() -> LLMDeckAbstract:
    return get_pipelex_hub().get_required_llm_deck()


def get_plugin_manager() -> PluginManager:
    return get_pipelex_hub().get_plugin_manager()


def get_inference_manager() -> InferenceManagerProtocol:
    return get_pipelex_hub().get_inference_manager()


def get_llm_worker(
    llm_handle: str,
    specific_llm_engine_blueprint: Optional[LLMEngineBlueprint] = None,
) -> LLMWorkerAbstract:
    return get_inference_manager().get_llm_worker(
        llm_handle=llm_handle,
        specific_llm_engine_blueprint=specific_llm_engine_blueprint,
    )


def get_imgg_worker(
    imgg_handle: str,
) -> ImggWorkerAbstract:
    return get_inference_manager().get_imgg_worker(imgg_handle=imgg_handle)


def get_ocr_worker(
    ocr_handle: str,
) -> OcrWorkerAbstract:
    return get_inference_manager().get_ocr_worker(ocr_handle=ocr_handle)


def get_report_delegate() -> InferenceReportDelegate:
    return get_pipelex_hub().get_report_delegate()


def get_content_generator() -> ContentGeneratorProtocol:
    return get_pipelex_hub().get_required_content_generator()


# pipelex


def get_secret(secret_id: str) -> str:
    return get_secrets_provider().get_secret(secret_id=secret_id)


def get_domain_provider() -> DomainProviderAbstract:
    return get_pipelex_hub().get_required_domain_provider()


def get_domains(excluded_domains: Optional[List[str]] = None) -> List[Domain]:
    domains = get_pipelex_hub().get_required_domain_provider().get_domains()
    if excluded_domains:
        domains = [domain for domain in domains if domain.code not in excluded_domains]
    return domains


def get_required_domain(domain_code: str) -> Domain:
    return get_pipelex_hub().get_required_domain_provider().get_required_domain(domain_code=domain_code)


def get_optional_domain(domain_code: str) -> Optional[Domain]:
    if domain_provider := get_pipelex_hub().get_optional_domain_provider():
        return domain_provider.get_domain(domain_code=domain_code)
    else:
        return None


def get_pipe_provider() -> PipeProviderAbstract:
    return get_pipelex_hub().get_required_pipe_provider()


def get_pipes_by_domain(excluded_domains: Optional[List[str]] = None) -> Dict[str, List[str]]:
    pipes = get_pipe_provider().get_pipes()
    pipes_by_domain: Dict[str, List[str]] = defaultdict(list)
    for pipe in pipes:
        if excluded_domains and pipe.domain in excluded_domains:
            continue
        pipes_by_domain[pipe.domain].append(pipe.code)
    return pipes_by_domain


def get_required_pipe(pipe_code: str) -> PipeAbstract:
    return get_pipelex_hub().get_required_pipe_provider().get_required_pipe(pipe_code=pipe_code)


def get_optional_pipe(pipe_code: str) -> Optional[PipeAbstract]:
    return get_pipelex_hub().get_required_pipe_provider().get_optional_pipe(pipe_code=pipe_code)


def get_concept_provider() -> ConceptProviderAbstract:
    return get_pipelex_hub().get_required_concept_provider()


def get_optional_concept_provider() -> Optional[ConceptProviderAbstract]:
    return get_pipelex_hub().get_optional_concept_provider()


def get_required_concept(concept_code: str) -> Concept:
    return get_pipelex_hub().get_required_concept_provider().get_required_concept(concept_code=concept_code)


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
