import inspect
import os
from importlib.metadata import metadata
from typing import cast

from kajson.class_registry import ClassRegistry
from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager
from kajson.singleton import MetaSingleton
from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import (
    ContentGeneratorProtocol,
)
from pipelex.cogt.exceptions import InferenceBackendCredentialsError, RoutingProfileLibraryNotFoundError
from pipelex.cogt.inference.inference_manager import InferenceManager
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import PipelexConfig, get_config
from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.pipes.pipe_library import PipeLibrary
from pipelex.core.registry_models import PipelexRegistryModels
from pipelex.exceptions import PipelexConfigError, PipelexSetupError
from pipelex.hub import PipelexHub, get_observer_provider, set_pipelex_hub
from pipelex.libraries.library_manager_factory import LibraryManagerFactory
from pipelex.observer.local_observer import LocalObserver
from pipelex.pipe_works.pipe_router import PipeRouter
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.activity.activity_manager import ActivityManager
from pipelex.pipeline.activity.activity_manager_protocol import (
    ActivityManagerNoOp,
    ActivityManagerProtocol,
)
from pipelex.pipeline.pipeline_manager import PipelineManager
from pipelex.pipeline.track.pipeline_tracker import PipelineTracker
from pipelex.pipeline.track.pipeline_tracker_protocol import (
    PipelineTrackerNoOp,
    PipelineTrackerProtocol,
)
from pipelex.plugins.plugin_manager import PluginManager
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.reporting.reporting_protocol import ReportingNoOp, ReportingProtocol
from pipelex.test_extras.registry_test_models import PipelexTestModels
from pipelex.tools.config.config_root import ConfigRoot
from pipelex.tools.func_registry import func_registry
from pipelex.tools.runtime_manager import runtime_manager
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.templating.template_library import TemplateLibrary
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import Self

PACKAGE_NAME = __name__.split(".", maxsplit=1)[0]
PACKAGE_VERSION = metadata(PACKAGE_NAME)["Version"]


class Pipelex(metaclass=MetaSingleton):
    def __init__(
        self,
        config_dir_path: str,
        # Dependency injection
        pipelex_hub: PipelexHub | None = None,
        config_cls: type[ConfigRoot] | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        template_provider: TemplateLibrary | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        pipeline_manager: PipelineManager | None = None,
        pipeline_tracker: PipelineTracker | None = None,
        activity_manager: ActivityManagerProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        self.config_dir_path = config_dir_path
        self.pipelex_hub = pipelex_hub or PipelexHub()
        set_pipelex_hub(self.pipelex_hub)

        # tools
        try:
            self.pipelex_hub.setup_config(config_cls=config_cls or PipelexConfig)
        except ValidationError as exc:
            formatted_error_msg = format_pydantic_validation_error(exc)
            msg = f"Could not setup config because of: {formatted_error_msg}"
            raise PipelexConfigError(msg) from exc

        log.configure(
            project_name=get_config().project_name or "unknown_project",
            log_config=get_config().pipelex.log_config,
        )
        log.debug("Logs are configured")

        # tools
        self.template_provider = template_provider or TemplateLibrary.make_empty(config_dir_path=config_dir_path)
        self.pipelex_hub.set_template_provider(self.template_provider)

        self.class_registry = class_registry or ClassRegistry()
        self.pipelex_hub.set_class_registry(self.class_registry)
        self.kajson_manager = KajsonManager(class_registry=self.class_registry)

        # cogt
        self.plugin_manager = PluginManager()
        self.pipelex_hub.set_plugin_manager(self.plugin_manager)

        self.models_manager: ModelManagerAbstract = models_manager or ModelManager()
        self.pipelex_hub.set_models_manager(models_manager=self.models_manager)

        self.inference_manager = inference_manager or InferenceManager()
        self.pipelex_hub.set_inference_manager(self.inference_manager)

        self.reporting_delegate: ReportingProtocol
        if get_config().pipelex.feature_config.is_reporting_enabled:
            self.reporting_delegate = reporting_delegate or ReportingManager(reporting_config=get_config().pipelex.reporting_config)
        else:
            self.reporting_delegate = ReportingNoOp()
        self.pipelex_hub.set_report_delegate(self.reporting_delegate)

        # pipelex libraries
        domain_library = DomainLibrary.make_empty()
        concept_library = ConceptLibrary.make_empty()
        pipe_library = PipeLibrary.make_empty()
        self.pipelex_hub.set_domain_provider(domain_provider=domain_library)
        self.pipelex_hub.set_concept_provider(concept_provider=concept_library)
        self.pipelex_hub.set_pipe_provider(pipe_provider=pipe_library)

        self.library_manager = LibraryManagerFactory.make(
            domain_library=domain_library,
            concept_library=concept_library,
            pipe_library=pipe_library,
            config_dir_path=config_dir_path,
        )
        self.pipelex_hub.set_library_manager(library_manager=self.library_manager)

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

        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} init done")

    def setup(
        self,
        secrets_provider: SecretsProviderAbstract | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        storage_provider: StorageProviderAbstract | None = None,
    ):
        # tools
        self.pipelex_hub.set_secrets_provider(secrets_provider or EnvSecretsProvider())
        self.pipelex_hub.set_storage_provider(storage_provider)
        # cogt
        self.plugin_manager.setup()
        try:
            self.models_manager.setup()
        except RoutingProfileLibraryNotFoundError as routing_profile_library_exc:
            msg = "The routing library could not be found, please call `pipelex init config` to create it"
            raise PipelexSetupError(msg) from routing_profile_library_exc
        except InferenceBackendCredentialsError as credentials_exc:
            backend_name = credentials_exc.backend_name
            var_name = credentials_exc.key_name
            error_msg: str
            if secrets_provider:
                error_msg = (
                    f"Could not get credentials for inference backend {backend_name}:\n{credentials_exc},"
                    f"\ncheck that secret '{var_name}' is available from your secrets provider."
                )
            else:
                error_msg = (
                    f"Could not get credentials for inference backend {backend_name}:\n{credentials_exc},\n"
                    f"you need to add '{var_name}' to your environment variables or to your .env file."
                )
            if credentials_exc.backend_name == "pipelex_inference":
                error_msg += (
                    "\nYou can check the project's README about getting a Pipelex Inference API key,\n\n"
                    "or you can bring your own 'OPENAI_API_KEY', "
                    "'AZURE_OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'MISTRAL_API_KEY' etc.\n"
                    "--> choose which inference backends to enable in .pipelex/inference/backends.toml\n"
                )
            raise PipelexSetupError(error_msg) from credentials_exc
        self.pipelex_hub.set_content_generator(content_generator or ContentGenerator())
        self.reporting_delegate.setup()
        self.class_registry.register_classes(PipelexRegistryModels.get_all_models())
        if runtime_manager.is_unit_testing:
            log.debug("Registering test models for unit testing")
            self.class_registry.register_classes(PipelexTestModels.get_all_models())
        self.activity_manager.setup()

        self.pipelex_hub.set_observer_provider(observer_provider=LocalObserver())

        self.pipelex_hub.set_pipe_router(pipe_router or PipeRouter(observer_provider=get_observer_provider()))

        # pipeline
        self.pipeline_tracker.setup()
        self.pipeline_manager.setup()

        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} setup done for {get_config().project_name}")

    def setup_libraries(self):
        try:
            self.template_provider.setup()
            self.library_manager.setup()
            self.library_manager.load_libraries()
        except ValidationError as exc:
            formatted_error_msg = format_pydantic_validation_error(exc)
            msg = f"Could not setup libraries because of: {formatted_error_msg}"
            raise PipelexSetupError(msg) from exc
        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} setup libraries done for {get_config().project_name}")

    def validate_libraries(self):
        try:
            self.library_manager.validate_libraries()
        except ValidationError as exc:
            formatted_error_msg = format_pydantic_validation_error(exc)
            msg = f"Could not validate libraries because of: {formatted_error_msg}"
            raise PipelexSetupError(msg) from exc
        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} validate libraries done for {get_config().project_name}")

    def teardown(self):
        # pipelex
        self.pipeline_manager.teardown()
        self.pipeline_tracker.teardown()
        self.library_manager.teardown()
        self.template_provider.teardown()
        self.activity_manager.teardown()

        # cogt
        self.inference_manager.teardown()
        self.reporting_delegate.teardown()
        self.plugin_manager.teardown()

        # tools
        self.kajson_manager.teardown()
        self.class_registry.teardown()
        func_registry.teardown()

        log.debug(f"{PACKAGE_NAME} version {PACKAGE_VERSION} teardown done for {get_config().project_name} (except config & logs)")
        self.pipelex_hub.reset_config()
        # Clear the singleton instance from metaclass
        if self.__class__ in MetaSingleton.instances:
            del MetaSingleton.instances[self.__class__]

    # TODO: add kwargs to make() so that subclasses can employ specific parameters
    @classmethod
    def make(
        cls,
        relative_config_folder_path: str | None = None,
        absolute_config_folder_path: str | None = None,
        from_file: bool | None = True,
    ) -> Self:
        """Create and initialize a Pipelex instance.

        Args:
            relative_config_folder_path: Path to config folder relative to either the caller file or current working directory.
                Cannot be used together with absolute_config_folder_path.
            absolute_config_folder_path: Absolute path to config folder.
                Cannot be used together with relative_config_folder_path.
            from_file: Only used when relative_config_folder_path is provided.
                If True (default), the relative path is resolved relative to the file where make() was called.
                If False, the relative path is resolved relative to the current working directory (useful for CLI scenarios).

        Returns:
            Initialized Pipelex instance.

        Raises:
            PipelexSetupError: If both relative_config_folder_path and absolute_config_folder_path are provided.
            Or if frame inspection fails when using relative paths with from_file=True.

        Note:
            If neither path is provided, defaults to "./pipelex_libraries".

        """
        if relative_config_folder_path is not None and absolute_config_folder_path is not None:
            msg = "Cannot specify both relative_config_folder_path and absolute_config_folder_path"
            raise PipelexSetupError(msg)

        if relative_config_folder_path is not None:
            if from_file:
                current_frame = inspect.currentframe()
                if current_frame is None:
                    msg = "Could not find relative config folder path because of: Failed to get current frame"
                    raise PipelexSetupError(msg)
                if current_frame.f_back is None:
                    msg = "Could not find relative config folder path because of: Failed to get caller frame"
                    raise PipelexSetupError(msg)
                caller_file = current_frame.f_back.f_code.co_filename
                caller_dir = os.path.dirname(os.path.abspath(caller_file))
                config_dir_path = os.path.abspath(os.path.join(caller_dir, relative_config_folder_path))
            else:
                config_dir_path = os.path.abspath(os.path.join(os.getcwd(), relative_config_folder_path))
        elif absolute_config_folder_path is not None:
            config_dir_path = absolute_config_folder_path
        else:
            config_dir_path = "./pipelex_libraries"

        pipelex_instance = cls(config_dir_path=config_dir_path)
        pipelex_instance.setup()
        pipelex_instance.setup_libraries()
        return pipelex_instance

    @classmethod
    def get_optional_instance(cls) -> Self | None:
        instance = MetaSingleton.instances.get(cls)
        return cast("Self | None", instance)

    @classmethod
    def get_instance(cls) -> Self:
        instance = MetaSingleton.instances.get(cls)
        if instance is None:
            msg = "Pipelex is not initialized"
            raise RuntimeError(msg)
        return cast("Self", instance)
