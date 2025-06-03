from importlib.metadata import metadata
from typing import Any, ClassVar, List, Optional, Type

from dotenv import load_dotenv
from kajson.class_registry import class_registry
from pydantic import ValidationError
from rich import print
from typing_extensions import Self

from pipelex import log
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.inference.inference_manager import InferenceManager
from pipelex.cogt.inference.inference_report_manager import InferenceReportManager
from pipelex.cogt.llm.llm_models.llm_model import LATEST_VERSION_NAME
from pipelex.cogt.llm.llm_models.llm_model_library import LLMModelLibrary
from pipelex.cogt.plugin_manager import PluginManager
from pipelex.config import PipelexConfig, get_config
from pipelex.core.registry_models import PipelexRegistryModels
from pipelex.exceptions import PipelexConfigError, PipelexSetupError
from pipelex.hub import PipelexHub, set_pipelex_hub
from pipelex.libraries.library_manager import LibraryManager
from pipelex.pipe_works.pipe_router import PipeRouter
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.activity.activity_manager import ActivityManager
from pipelex.pipeline.activity.activity_manager_protocol import ActivityManagerNoOp, ActivityManagerProtocol
from pipelex.pipeline.pipeline_manager import PipelineManager
from pipelex.pipeline.track.pipeline_tracker import PipelineTracker
from pipelex.pipeline.track.pipeline_tracker_protocol import PipelineTrackerNoOp, PipelineTrackerProtocol
from pipelex.test_extras.registry_test_models import PipelexTestModels
from pipelex.tools.config.models import ConfigRoot
from pipelex.tools.func_registry import func_registry
from pipelex.tools.runtime_manager import runtime_manager
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.templating.template_library import TemplateLibrary
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

PACKAGE_NAME = __name__.split(".", maxsplit=1)[0]
PACKAGE_VERSION = metadata(PACKAGE_NAME)["Version"]


class Pipelex:
    _pipelex_instance: ClassVar[Optional[Self]] = None

    def __new__(
        cls,
        pipelex_cls: Optional[Type[Self]] = None,
        pipelex_hub: Optional[PipelexHub] = None,
        config_cls: Optional[Type[ConfigRoot]] = None,
        ready_made_config: Optional[ConfigRoot] = None,
        template_provider: Optional[TemplateLibrary] = None,
        llm_model_provider: Optional[LLMModelLibrary] = None,
        plugin_manager: Optional[PluginManager] = None,
        inference_manager: Optional[InferenceManager] = None,
        pipeline_manager: Optional[PipelineManager] = None,
        pipeline_tracker: Optional[PipelineTracker] = None,
        activity_manager: Optional[ActivityManagerProtocol] = None,
    ) -> Self:
        if cls._pipelex_instance is not None:
            raise RuntimeError(
                "Pipelex is a singleton, it is instantiated only once. Its instance is private. All you need is accesible through the hub."
            )
        if pipelex_cls is None:
            pipelex_cls = cls

        if not issubclass(pipelex_cls, cls):
            raise TypeError(f"{pipelex_cls!r} is not a subclass of {cls.__name__}")

        return super().__new__(pipelex_cls)

    def __init__(
        self,
        pipelex_cls: Optional[Type[Self]] = None,
        pipelex_hub: Optional[PipelexHub] = None,
        config_cls: Optional[Type[ConfigRoot]] = None,
        ready_made_config: Optional[ConfigRoot] = None,
        template_provider: Optional[TemplateLibrary] = None,
        llm_model_provider: Optional[LLMModelLibrary] = None,
        plugin_manager: Optional[PluginManager] = None,
        inference_manager: Optional[InferenceManager] = None,
        pipeline_manager: Optional[PipelineManager] = None,
        pipeline_tracker: Optional[PipelineTracker] = None,
        activity_manager: Optional[ActivityManagerProtocol] = None,
    ) -> None:
        self.pipelex_hub = pipelex_hub or PipelexHub()
        set_pipelex_hub(self.pipelex_hub)

        # tools
        if ready_made_config is not None:
            if config_cls is not None:
                raise PipelexConfigError("config_cls must be None when ready_made_config is provided")
            self.pipelex_hub.set_config(ready_made_config)
        else:
            if config_cls is None:
                config_cls = PipelexConfig
            try:
                self.pipelex_hub.setup_config(config_cls=config_cls)
            except ValidationError as exc:
                error_msg = format_pydantic_validation_error(exc)
                raise PipelexConfigError(f"Error because of: {error_msg}") from exc
        for extra_env_file in get_config().pipelex.extra_env_files:
            load_dotenv(dotenv_path=extra_env_file, override=True)
        log.configure(
            project_name=get_config().project_name or "unknown_project",
            log_config=get_config().pipelex.log_config,
        )
        log.debug("Logs are configured")

        # tools
        self.template_provider = template_provider or TemplateLibrary()
        self.pipelex_hub.set_template_provider(self.template_provider)

        # cogt
        self.llm_model_provider = llm_model_provider or LLMModelLibrary()
        self.pipelex_hub.set_llm_models_provider(self.llm_model_provider)
        self.plugin_manager = plugin_manager or PluginManager()
        self.pipelex_hub.set_plugin_manager(self.plugin_manager)
        self.inference_manager = inference_manager or InferenceManager()
        self.pipelex_hub.set_inference_manager(self.inference_manager)

        self.report_manager = InferenceReportManager(report_config=get_config().cogt.cogt_report_config)
        self.pipelex_hub.set_report_delegate(self.report_manager)

        # pipelex libraries
        self.library_manager = LibraryManager()
        self.pipelex_hub.set_domain_provider(domain_provider=self.library_manager.domain_library)
        self.pipelex_hub.set_concept_provider(concept_provider=self.library_manager.concept_library)
        self.pipelex_hub.set_pipe_provider(pipe_provider=self.library_manager.pipe_library)

        # pipelex pipeline
        self.pipeline_tracker: PipelineTrackerProtocol
        if pipeline_tracker:
            self.pipeline_tracker = pipeline_tracker
        elif get_config().pipelex.feature_config.is_pipeline_tracking_enabled:
            self.pipeline_tracker = PipelineTracker(tracker_config=get_config().pipelex.tracker_config)
        else:
            self.pipeline_tracker = PipelineTrackerNoOp()
        self.pipelex_hub.set_pipeline_tracker(pipeline_tracker=self.pipeline_tracker)
        self.pipeline_manager = pipeline_manager or PipelineManager()
        self.pipelex_hub.set_pipeline_manager(pipeline_manager=self.pipeline_manager)

        self.activity_manager: ActivityManagerProtocol
        if activity_manager:
            self.activity_manager = activity_manager
        elif get_config().pipelex.feature_config.is_activity_tracking_enabled:
            self.activity_manager = ActivityManager()
        else:
            self.activity_manager = ActivityManagerNoOp()
        self.pipelex_hub.set_activity_manager(activity_manager=self.activity_manager)

        Pipelex._pipelex_instance = self
        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} init done")

    def setup(
        self,
        secrets_provider: Optional[SecretsProviderAbstract] = None,
        content_generator: Optional[ContentGeneratorProtocol] = None,
        pipe_router: Optional[PipeRouterProtocol] = None,
        structure_classes: Optional[List[Type[Any]]] = None,
    ):
        # tools
        self.pipelex_hub.set_secrets_provider(secrets_provider or EnvSecretsProvider())

        # cogt
        self.pipelex_hub.set_content_generator(content_generator or ContentGenerator())
        self.report_manager.setup()
        class_registry.register_classes(PipelexRegistryModels.get_all_models())
        if runtime_manager.is_unit_testing:
            log.debug("Registering test models for unit testing")
            class_registry.register_classes(PipelexTestModels.get_all_models())
        self.activity_manager.setup()

        if structure_classes:
            class_registry.register_classes(structure_classes)

        self.pipelex_hub.set_pipe_router(pipe_router or PipeRouter())

        # pipeline
        self.pipeline_tracker.setup()
        self.pipeline_manager.setup()

        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} setup done for {get_config().project_name}")

    def finish_setup(self):
        try:
            self.template_provider.setup()
            self.llm_model_provider.setup()
            llm_deck = self.library_manager.load_deck()
            for llm_model in self.llm_model_provider.get_all_llm_models():
                if llm_model.version == LATEST_VERSION_NAME:
                    llm_deck.add_llm_handle_to_llm_engine_blueprint(
                        llm_handle=llm_model.llm_name,
                        llm_engine_default=llm_model.llm_name,
                    )
            llm_deck.validate_llm_presets()
            self.library_manager.load_libraries()
            if self.library_manager.llm_deck is None:
                raise PipelexSetupError("LLM deck is not loaded")
            self.pipelex_hub.set_llm_deck_provider(llm_deck_provider=self.library_manager.llm_deck)
            self.library_manager.validate_libraries()
        except ValidationError as exc:
            error_msg = format_pydantic_validation_error(exc)
            raise PipelexSetupError(f"Error because of: {error_msg}") from exc
        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} finish setup done for {get_config().project_name}")

    def teardown(self):
        # pipelex
        self.pipeline_manager.teardown()
        self.pipeline_tracker.teardown()
        self.library_manager.teardown()
        self.template_provider.teardown()
        self.activity_manager.teardown()

        # cogt
        self.inference_manager.teardown()
        self.report_manager.teardown()
        self.llm_model_provider.teardown()

        # tools
        class_registry.reset()
        func_registry.teardown()

        Pipelex._pipelex_instance = None
        project_name = get_config().project_name
        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} teardown done for {get_config().project_name} (except config & logs)")
        self.pipelex_hub.reset_config()
        print(f"{PACKAGE_NAME} version {PACKAGE_VERSION} config reset done for {project_name}")

    # TODO: add kwargs to make() so that subclasses can employ specific parameters
    @classmethod
    def make(cls, structure_classes: Optional[List[Type[Any]]] = None) -> Self:
        pipelex_instance = cls()
        pipelex_instance.setup(structure_classes=structure_classes)
        pipelex_instance.finish_setup()
        log.info(f"Pipelex {PACKAGE_VERSION} initialized.")
        return pipelex_instance
