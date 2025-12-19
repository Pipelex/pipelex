import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kajson.class_registry import ClassRegistry
from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager
from pydantic import ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError, PipelexSetupError
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import (
    ContentGeneratorProtocol,
)
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.exceptions import (
    InferenceBackendCredentialsError,
    InferenceBackendLibraryNotFoundError,
    InferenceBackendLibraryValidationError,
    ModelDeckNotFoundError,
    ModelDeckValidationError,
    RoutingProfileDisabledBackendError,
    RoutingProfileLibraryNotFoundError,
)
from pipelex.cogt.inference.inference_manager import InferenceManager
from pipelex.cogt.model_backends.backend_credentials import (
    BackendCredentialsErrorMsgFactory,
)
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.core.registry_models import CoreRegistryModels
from pipelex.core.validation import report_validation_error
from pipelex.hub import PipelexHub, set_pipelex_hub
from pipelex.libraries.library_manager import LibraryManager
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.observer.local_observer import LocalObserver
from pipelex.observer.multi_observer import MultiObserver
from pipelex.observer.observer_protocol import ObserverProtocol
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.pipeline_manager import PipelineManager
from pipelex.pipeline.track.pipeline_tracker import PipelineTracker
from pipelex.pipeline.track.pipeline_tracker_protocol import (
    PipelineTrackerNoOp,
    PipelineTrackerProtocol,
)
from pipelex.plugins.plugin_manager import PluginManager
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.reporting.reporting_protocol import ReportingNoOp, ReportingProtocol
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.configuration.configs import ConfigPaths, PipelexConfig
from pipelex.system.pipelex_service.exceptions import (
    GatewayTermsNotAcceptedError,
)
from pipelex.system.pipelex_service.pipelex_service_config import (
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.system.registries.func_registry import func_registry
from pipelex.system.registries.singleton import MetaSingleton
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.system.telemetry.observer_telemetry import ObserverTelemetry
from pipelex.system.telemetry.telemetry_config import (
    TelemetryConfig,
)
from pipelex.system.telemetry.telemetry_factory import TelemetryFactory
from pipelex.system.telemetry.telemetry_manager_abstract import (
    TelemetryManagerAbstract,
)
from pipelex.test_extras.registry_test_models import TestRegistryModels
from pipelex.tools.misc.package_utils import get_package_info
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.types import Self
from pipelex.urls import URLs

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs
    from pipelex.system.pipelex_service.remote_config import RemoteConfig

PACKAGE_NAME, PACKAGE_VERSION = get_package_info()


class Pipelex(metaclass=MetaSingleton):
    def __init__(
        self,
        config_dir_path: str | None = None,
        config_cls: type[ConfigRoot] | None = None,
    ) -> None:
        self.is_pipelex_service_enabled = False  # Will be set during setup
        self.config_dir_path = config_dir_path or ConfigPaths.DEFAULT_CONFIG_DIR_PATH
        self.pipelex_hub = PipelexHub()
        set_pipelex_hub(self.pipelex_hub)

        # tools
        try:
            self.pipelex_hub.setup_config(config_cls=config_cls or PipelexConfig)
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="config", validation_error=validation_error)
            msg = f"Could not setup config because of: {validation_error_msg}"
            raise PipelexConfigError(msg) from validation_error

        log_config = get_config().pipelex.log_config
        self.pipelex_hub.set_console_print_target(target=log_config.console_print_target)
        log.configure(log_config=log_config)
        log.verbose("Logs are configured")

        # tools
        self.class_registry: ClassRegistryAbstract | None = None

        # cogt
        self.plugin_manager = PluginManager()
        self.pipelex_hub.set_plugin_manager(self.plugin_manager)

        self.reporting_delegate: ReportingProtocol | None = None
        self.telemetry_manager: TelemetryManagerAbstract | None = None
        # pipeline
        self.pipeline_tracker: PipelineTrackerProtocol | None = None
        self.library_manager: LibraryManagerAbstract | None = None

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} init done")

    @staticmethod
    def _get_config_file_not_found_error_msg(component_name: str) -> str:
        """Generate error message for missing config files."""
        return f"Config files are missing for the {component_name}. Run `pipelex init config` to generate the missing files."

    @staticmethod
    def _get_validation_error_msg(component_name: str, validation_exc: Exception) -> str:
        """Generate error message for invalid config files."""
        msg = ""
        cause_exc = validation_exc.__cause__
        if cause_exc is None:
            msg += f"\nUnexpexted error:{cause_exc}"
            raise PipelexSetupError(msg) from cause_exc
        if not isinstance(cause_exc, ValidationError):
            msg += f"\nUnexpexted cause:{cause_exc}"
            raise PipelexSetupError(msg) from cause_exc
        report = report_validation_error(category="config", validation_error=cause_exc)
        return f"""{msg}
{report}

Config files are invalid for the {component_name}.
You can fix them manually, or run `pipelex init config --reset` to regenerate them.
Note that this command resets all config files to their default values.
If you need help, drop by our Discord: we're happy to assist: {URLs.discord}.
"""

    def setup(
        self,
        integration_mode: IntegrationMode,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipeline_manager: PipelineManager | None = None,
        pipeline_tracker: PipelineTracker | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        library_manager: LibraryManagerAbstract | None = None,
        **kwargs: Any,
    ):
        if kwargs:
            msg = f"The base setup method does not support any additional arguments: {kwargs}"
            raise PipelexSetupError(msg)

        # Initialize secrets provider early - needed for gateway check
        secrets_provider = secrets_provider or EnvSecretsProvider()

        # --- Pipelex Service and Telemetry --------------------------------------------------

        # Check if Pipelex Gateway is enabled
        # for now the only servic is the Pipelex Gateway
        is_pipelex_service_enabled = is_pipelex_gateway_enabled()

        remote_config: RemoteConfig | None = None
        gateway_model_specs: BackendModelSpecs | None = None
        if is_pipelex_service_enabled:
            # Skip terms check for CI mode - automated CI/CD pipelines don't require human consent
            if integration_mode.requires_terms_acceptance:
                # Check if terms are accepted
                pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.pipelex_config_dir)
                if pipelex_service_config is None or not pipelex_service_config.agreement.terms_accepted:
                    raise GatewayTermsNotAcceptedError
            # Fetch remote configuration
            remote_config = RemoteConfigFetcher.fetch_remote_config()
            log.verbose("Successfully fetched Pipelex Gateway remote configuration")
            gateway_model_specs = remote_config.backend_model_specs

        self.telemetry_manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=secrets_provider,
            integration_mode=integration_mode,
            remote_config=remote_config,
            is_pipelex_telemetry_enabled=is_pipelex_service_enabled,
            telemetry_config=telemetry_config,
            injected_telemetry_manager=telemetry_manager,
        )
        self.telemetry_manager.setup(integration_mode=integration_mode)
        self.pipelex_hub.set_telemetry_manager(telemetry_manager=self.telemetry_manager)

        # --- Tools ----------------------------------------------------------------------------

        self.class_registry = class_registry or ClassRegistry()
        self.pipelex_hub.set_class_registry(self.class_registry)
        self.kajson_manager = KajsonManager(class_registry=self.class_registry)
        self.pipelex_hub.set_secrets_provider(secrets_provider=secrets_provider)
        self.pipelex_hub.set_storage_provider(storage_provider)

        self.library_manager = library_manager or LibraryManager()
        self.pipelex_hub.set_library_manager(library_manager=self.library_manager)

        # --- AI Models and Inference Management ------------------------------------------------

        self.plugin_manager.setup()

        self.models_manager: ModelManagerAbstract = models_manager or ModelManager()
        self.pipelex_hub.set_models_manager(models_manager=self.models_manager)

        try:
            self.models_manager.setup(
                secrets_provider=secrets_provider,
                gateway_model_specs=gateway_model_specs,
            )
        except RoutingProfileLibraryNotFoundError as routing_not_found_exc:
            msg = self._get_config_file_not_found_error_msg("routing profile library")
            raise PipelexSetupError(msg) from routing_not_found_exc
        except InferenceBackendLibraryNotFoundError as backend_not_found_exc:
            msg = self._get_config_file_not_found_error_msg("inference backend library")
            raise PipelexSetupError(msg) from backend_not_found_exc
        except ModelDeckNotFoundError as deck_not_found_exc:
            msg = self._get_config_file_not_found_error_msg("model deck")
            raise PipelexSetupError(msg) from deck_not_found_exc
        except RoutingProfileDisabledBackendError as routing_profile_exc:
            msg = f"Some backend(s) required for a routing profile is not enabled: {routing_profile_exc}"
            raise PipelexSetupError(msg) from routing_profile_exc

        except InferenceBackendLibraryValidationError as backend_validation_exc:
            msg = self._get_validation_error_msg("inference backend library", backend_validation_exc)
            raise PipelexSetupError(msg) from backend_validation_exc
        except ModelDeckValidationError as deck_validation_exc:
            msg = self._get_validation_error_msg("model deck", deck_validation_exc)
            msg += "\n\nIf you added your own config files to the model deck then you'll have to change them manually."
            raise PipelexSetupError(msg) from deck_validation_exc

        except InferenceBackendCredentialsError as credentials_exc:
            backend_name = credentials_exc.backend_name
            var_name = credentials_exc.key_name
            error_msg = BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg(
                secrets_provider=secrets_provider,
                backend_name=backend_name,
                var_name=var_name,
            )
            raise PipelexSetupError(error_msg) from credentials_exc
        if content_generator:
            self.pipelex_hub.set_content_generator(content_generator)
        else:
            storage_provider = storage_provider or LocalStorageProvider(root_path=Path(".pipelex/storage"))
            generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
            self.pipelex_hub.set_content_generator(ContentGenerator(generated_content_factory=generated_content_factory))

        self.inference_manager = inference_manager or InferenceManager()
        self.pipelex_hub.set_inference_manager(self.inference_manager)

        # --- Pipeline Tracking (deprecated) ----------------------------------------------------

        if pipeline_tracker:
            self.pipeline_tracker = pipeline_tracker
        elif get_config().pipelex.feature_config.is_pipeline_tracking_enabled:
            self.pipeline_tracker = PipelineTracker(tracker_config=get_config().pipelex.tracker_config)
        else:
            self.pipeline_tracker = PipelineTrackerNoOp()
        self.pipelex_hub.set_pipeline_tracker(pipeline_tracker=self.pipeline_tracker)
        self.pipeline_tracker.setup()

        # --- Libraries & Registries -------------------------------------------------------------

        if get_config().pipelex.feature_config.is_reporting_enabled:
            self.reporting_delegate = reporting_delegate or ReportingManager()
        else:
            self.reporting_delegate = ReportingNoOp()
        self.pipelex_hub.set_report_delegate(self.reporting_delegate)
        self.reporting_delegate.setup()

        self.library_manager = library_manager or LibraryManager()
        self.pipelex_hub.set_library_manager(library_manager=self.library_manager)

        self.pipeline_manager = pipeline_manager or PipelineManager()
        self.pipelex_hub.set_pipeline_manager(pipeline_manager=self.pipeline_manager)
        self.pipeline_manager.setup()

        self.class_registry.register_classes(CoreRegistryModels.get_all_models())
        if runtime_manager.is_unit_testing:
            log.verbose("Registering test models for unit testing")
            self.class_registry.register_classes(TestRegistryModels.get_all_models())

        # --- Observers -------------------------------------------------------------------------

        if not observers:
            local_observer = LocalObserver()
            observer_telemetry = ObserverTelemetry(telemetry_manager=self.telemetry_manager)
            observers = {"local": local_observer, "telemetry": observer_telemetry}
        multi_observer = MultiObserver(observers=observers)
        self.pipelex_hub.set_observer(observer=multi_observer)

        # --- Pipe Router -----------------------------------------------------------------------

        self.pipelex_hub.set_pipe_router(pipe_router or PipeRouter(observer=multi_observer))

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} setup done")

    def teardown(self):
        # pipelex
        self.pipeline_manager.teardown()
        if self.pipeline_tracker:
            self.pipeline_tracker.teardown()
        if self.telemetry_manager:
            self.telemetry_manager.teardown()

        # cogt
        self.inference_manager.teardown()
        if self.reporting_delegate:
            self.reporting_delegate.teardown()
        self.plugin_manager.teardown()

        # tools
        self.kajson_manager.teardown()
        if self.class_registry:
            self.class_registry.teardown()
        func_registry.teardown()

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} teardown done (except config & logs)")
        self.pipelex_hub.reset_config()
        # Clear the singleton instance from metaclass
        if self.__class__ in MetaSingleton.instances:
            del MetaSingleton.instances[self.__class__]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> None:
        self.teardown()

    @classmethod
    def make(
        cls,
        integration_mode: IntegrationMode = IntegrationMode.PYTHON,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipeline_manager: PipelineManager | None = None,
        pipeline_tracker: PipelineTracker | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        **kwargs: Any,
    ) -> Self:
        """Create and initialize a Pipelex singleton instance.

        All parameters are optional dependency injections. If None, default implementations
        are used during setup. This enables customization of core components like secrets
        management, storage, model routing, and pipeline execution.

        Args:
            integration_mode: Integration mode (CLI, FASTAPI, DOCKER, MCP, N8N, PYTHON, PYTEST)
            class_registry: Custom class registry for dynamic loading
            secrets_provider: Custom secrets/credentials provider
            storage_provider: Custom storage backend
            models_manager: Custom model configuration manager
            inference_manager: Custom inference routing manager
            content_generator: Custom content generation implementation
            pipeline_manager: Custom pipeline management
            pipeline_tracker: Custom pipeline tracking/logging
            pipe_router: Custom pipe routing logic
            reporting_delegate: Custom reporting handler
            telemetry_config: Custom telemetry configuration
            telemetry_manager: Custom telemetry manager
            observers: Custom observers for pipeline events
            **kwargs: Additional configuration options, only supported by your own subclass of Pipelex if you really need one

        Returns:
            Initialized Pipelex instance.

        Raises:
            PipelexSetupError: If Pipelex is already initialized or setup fails

        """
        if cls.get_optional_instance() is not None:
            msg = "Pipelex is already initialized"
            raise PipelexSetupError(msg)

        pipelex_instance = cls()
        try:
            pipelex_instance.setup(
                integration_mode=integration_mode,
                class_registry=class_registry,
                secrets_provider=secrets_provider,
                storage_provider=storage_provider,
                models_manager=models_manager,
                inference_manager=inference_manager,
                content_generator=content_generator,
                pipeline_manager=pipeline_manager,
                pipeline_tracker=pipeline_tracker,
                pipe_router=pipe_router,
                reporting_delegate=reporting_delegate,
                telemetry_config=telemetry_config,
                telemetry_manager=telemetry_manager,
                observers=observers,
                **kwargs,
            )
            pipelex_instance.models_manager.validate_model_deck()
        except BaseException:
            # Cleanup the singleton instance if setup fails to avoid "already initialized" errors
            if cls in MetaSingleton.instances:
                del MetaSingleton.instances[cls]
            raise
        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} ready")
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

    @classmethod
    def teardown_if_needed(cls) -> None:
        """Teardown the Pipelex singleton instance if it exists.

        This is useful for cleanup in finally blocks where the instance
        may or may not have been successfully created.
        """
        instance = cls.get_optional_instance()
        if instance is not None:
            instance.teardown()
