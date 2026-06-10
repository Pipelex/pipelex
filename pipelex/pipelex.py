import types
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kajson.class_registry import ClassRegistry
from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager
from pydantic import ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError, PipelexSetupError
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
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
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.core.registry_models import CoreRegistryModels
from pipelex.core.stuffs.stuff_template_set import STUFF_TEMPLATE_SET
from pipelex.core.validation import report_validation_error
from pipelex.graph.mermaidflow.template_set import MERMAID_TEMPLATE_SET
from pipelex.graph.reactflow.template_set import REACTFLOW_TEMPLATE_SET
from pipelex.hub import PipelexHub, set_pipelex_hub
from pipelex.libraries.library_manager import LibraryManager
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.observer.multi_observer import MultiObserver
from pipelex.observer.observer_protocol import ObserverNoOp, ObserverProtocol
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipeline.pipeline_manager import PipelineManager
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.plugins.plugin_manager import PluginManager
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.reporting.reporting_protocol import ReportingNoOp, ReportingProtocol
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.environment import get_pipelexpath_dirs
from pipelex.system.pipelex_service.exceptions import (
    GatewayTermsNotAcceptedError,
    InferenceSetupRequiredError,
    RemoteConfigStaleWarning,
)
from pipelex.system.pipelex_service.pipelex_service_config import (
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.system.registries.func_registry import FuncRegistry, func_registry
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
from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry
from pipelex.tools.misc.package_utils import get_package_info
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.storage.storage_provider_factory import make_storage_provider_from_config
from pipelex.types import Self
from pipelex.urls import URLs

if TYPE_CHECKING:
    from pipelex.system.pipelex_service.remote_config import RemoteConfig
    from pipelex.system.pipelex_service.types import RemoteConfigSource

PACKAGE_NAME, PACKAGE_VERSION = get_package_info()


class Pipelex(metaclass=MetaSingleton):
    def __init__(
        self,
        config_dir_path: Path | None = None,
        config_cls: type[ConfigRoot] | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        # Readiness gate: flipped True only at the very end of make(), after setup() and the optional
        # validate_model_deck() both succeed. Readers (ensure_pipelex_booted) must gate on this, NOT on
        # mere registry presence -- MetaSingleton registers the instance before setup() configures the hub.
        self.is_ready: bool = False
        self.is_pipelex_service_enabled = False  # Will be set during setup
        self.config_dir_path = config_dir_path or config_manager.pipelex_config_dir
        self.pipelex_hub = PipelexHub()
        set_pipelex_hub(self.pipelex_hub)

        # tools
        try:
            self.pipelex_hub.setup_config(config_cls=config_cls or PipelexConfig, config_overrides=config_overrides)
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
        self.func_registry: FuncRegistry | None = None
        # cogt
        self.plugin_manager = PluginManager()
        self.pipelex_hub.set_plugin_manager(self.plugin_manager)

        self.reporting_delegate: ReportingProtocol | None = None
        self.telemetry_manager: TelemetryManagerAbstract | None = None
        # pipeline
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
You can fix them manually, or run `pipelex init config` to regenerate them.
Note that this command resets all config files to their default values.
If you need help, drop by our Discord: we're happy to assist: {URLs.discord}.
"""

    def setup(
        self,
        integration_mode: IntegrationMode,
        needs_inference: bool = True,
        temporal_enabled: bool | None = None,
        needs_model_specs: bool | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipeline_manager: PipelineManagerAbstract | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        library_manager: LibraryManagerAbstract | None = None,
        library_dirs: list[str] | list[Path] | None = None,
        **kwargs: Any,
    ):
        if kwargs:
            msg = f"The base setup method does not support any additional arguments: {kwargs}"
            raise PipelexSetupError(msg)

        # Override temporal.is_enabled if temporal_enabled is explicitly provided
        if temporal_enabled is not None:
            config = get_config()
            updated_temporal = config.temporal.model_copy(update={"is_enabled": temporal_enabled})
            config.temporal = updated_temporal

        self._temporal_task_manager: object | None = None

        # Initialize secrets provider early - needed for gateway check
        secrets_provider = secrets_provider or EnvSecretsProvider()

        # --- Pipelex Service and Telemetry --------------------------------------------------

        # Check if Pipelex Gateway is enabled
        # for now the only servic is the Pipelex Gateway
        is_pipelex_service_enabled = is_pipelex_gateway_enabled()

        effective_needs_model_specs = needs_model_specs if needs_model_specs is not None else needs_inference

        remote_config: RemoteConfig | None = None
        gateway_config: GatewayConfig | None = None
        gateway_config_source: RemoteConfigSource | None = None
        if is_pipelex_service_enabled:
            if not effective_needs_model_specs:
                # Use dummy config when inference is not needed (for testing without network access)
                remote_config = RemoteConfigFetcher.make_dummy_remote_config()
                gateway_model_specs = remote_config.backend_model_specs
                gateway_config = GatewayConfig(
                    model_specs=gateway_model_specs,
                    aws_region=remote_config.aws_region,
                )
                # Keep ``gateway_config_source`` as ``None``: the dummy specs are an empty
                # placeholder, not real Gateway data. ``ModelManager._enforce_gateway_model_membership``
                # treats ``source is None`` as "nothing to validate against," so the membership
                # check is skipped on this path — which is what we want for read-only flows like
                # ``pipelex-agent models`` without ``--backend``.
                log.verbose("Using dummy remote config (inference not needed)")
            else:
                # Terms acceptance is only required for actual inference usage, not for
                # read-only operations like fetching model specs for validation.
                # Also skip for CI mode — automated pipelines don't require human consent.
                if needs_inference and integration_mode.requires_terms_acceptance:
                    pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)
                    # First-run check: fires if inference has never been configured
                    # AND terms were never accepted (terms_accepted=true means existing
                    # user who already completed gateway setup before this flag existed).
                    if pipelex_service_config is None or (
                        not pipelex_service_config.onboarding.inference_setup_completed and not pipelex_service_config.agreement.terms_accepted
                    ):
                        raise InferenceSetupRequiredError
                    # Gateway terms check: this block only runs when gateway is
                    # enabled (is_pipelex_service_enabled guard above). BYOK users
                    # who disabled gateway via init skip this entire block.
                    if not pipelex_service_config.agreement.terms_accepted:
                        raise GatewayTermsNotAcceptedError
                # Fetch remote configuration (may fall back to on-disk cache when offline).
                remote_config_result = RemoteConfigFetcher.fetch_remote_config()
                remote_config = remote_config_result.config
                gateway_config_source = remote_config_result.source
                log.verbose(f"Successfully fetched Pipelex Gateway remote configuration (source={gateway_config_source})")
                gateway_model_specs = remote_config.backend_model_specs
                gateway_config = GatewayConfig(
                    model_specs=gateway_model_specs,
                    aws_region=remote_config.aws_region,
                )
                # Stale operation: warn loudly so machine consumers can re-surface the provenance.
                # Emission lives at this orchestration layer (not in the fetcher) so the fetcher
                # stays a pure data-returning function — and so test fixtures that swap in a
                # cached fetcher (tests/conftest.py) don't need to special-case warning replay.
                if gateway_config_source.is_cached:
                    cached_at_iso = remote_config_result.cached_at.isoformat() if remote_config_result.cached_at else "unknown"
                    warnings.warn(
                        f"Pipelex Gateway is running off a cached remote config (snapshot: {cached_at_iso}). "
                        "Run `pipelex init` while online to refresh.",
                        RemoteConfigStaleWarning,
                        stacklevel=2,
                    )

        # Disable Pipelex telemetry when:
        # - inference is not needed (no live runs to track), OR
        # - the gateway config came from the cache (stale specs imply potentially stale model
        #   identities; phoning home about pipe runs in that state would pollute metrics).
        gateway_source_is_cached = gateway_config_source is not None and gateway_config_source.is_cached
        is_pipelex_telemetry_enabled = is_pipelex_service_enabled and needs_inference and not gateway_source_is_cached
        self.telemetry_manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=secrets_provider,
            integration_mode=integration_mode,
            remote_config=remote_config,
            is_pipelex_telemetry_enabled=is_pipelex_telemetry_enabled,
            telemetry_config=telemetry_config,
            injected_telemetry_manager=telemetry_manager,
        )
        self.telemetry_manager.setup(integration_mode=integration_mode)
        self.pipelex_hub.set_telemetry_manager(telemetry_manager=self.telemetry_manager)

        # --- Tools ----------------------------------------------------------------------------

        self.class_registry = class_registry or ClassRegistry()
        self.pipelex_hub.set_class_registry(self.class_registry)
        self.kajson_manager = KajsonManager(class_registry=self.class_registry)

        self.func_registry = func_registry or FuncRegistry()
        self.pipelex_hub.set_func_registry(func_registry=self.func_registry)
        self.pipelex_hub.set_secrets_provider(secrets_provider=secrets_provider)
        if storage_provider is None:
            storage_config = get_config().pipelex.storage_config
            storage_provider = make_storage_provider_from_config(storage_config)
        self.pipelex_hub.set_storage_provider(storage_provider)

        # Register stuff templates first (used by mermaid, reactflow, and stuff_viewer)
        stuff_name, stuff_package, stuff_templates = STUFF_TEMPLATE_SET
        TemplateLoader.register_set(
            name=stuff_name,
            package=stuff_package,
            templates=stuff_templates,
        )
        reactflow_name, reactflow_package, reactflow_templates = REACTFLOW_TEMPLATE_SET
        TemplateLoader.register_set(
            name=reactflow_name,
            package=reactflow_package,
            templates=reactflow_templates,
        )
        mermaid_name, mermaid_package, mermaid_templates = MERMAID_TEMPLATE_SET
        TemplateLoader.register_set(
            name=mermaid_name,
            package=mermaid_package,
            templates=mermaid_templates,
        )
        TemplateLoader.load_all()

        self.library_manager = library_manager or LibraryManager()
        self.pipelex_hub.set_library_manager(library_manager=self.library_manager)

        # --- AI Models and Inference Management ------------------------------------------------

        self.plugin_manager.setup()

        self.models_manager: ModelManagerAbstract = models_manager or ModelManager()
        self.pipelex_hub.set_models_manager(models_manager=self.models_manager)

        try:
            self.models_manager.setup(
                secrets_provider=secrets_provider,
                gateway_config=gateway_config,
                gateway_config_source=gateway_config_source,
                needs_inference=needs_inference,
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

        if content_generator is None:
            if not needs_inference:
                content_generator = ContentGeneratorDry()
            elif get_config().temporal.is_enabled:
                from pipelex.temporal.tprl_content_generation.content_generator_in_workflow_factory import (  # noqa: PLC0415
                    ContentGeneratorInWorkflowFactory,
                )

                generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
                content_generator = ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow(
                    generated_content_factory=generated_content_factory,
                )
            else:
                generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
                content_generator = ContentGenerator(generated_content_factory=generated_content_factory)
        self.pipelex_hub.set_content_generator(content_generator)

        self.inference_manager = inference_manager or InferenceManager()
        self.pipelex_hub.set_inference_manager(self.inference_manager)

        # --- Libraries & Registries -------------------------------------------------------------

        if get_config().pipelex.feature_config.is_reporting_enabled:
            self.reporting_delegate = reporting_delegate or ReportingManager()
        else:
            self.reporting_delegate = ReportingNoOp()
        self.pipelex_hub.set_report_delegate(self.reporting_delegate)
        self.reporting_delegate.setup()

        self.library_manager = library_manager or LibraryManager()
        self.pipelex_hub.set_library_manager(library_manager=self.library_manager)

        # Resolve library_dirs: explicit value replaces PIPELEXPATH, otherwise use env var as fallback
        # When library_dirs is explicitly provided (even if empty), it overrides the env var
        if library_dirs is not None:
            resolved_library_dirs = [Path(dir_path) for dir_path in library_dirs]
            self.pipelex_hub.set_default_library_dirs(resolved_library_dirs)
        else:
            pipelexpath_dirs = get_pipelexpath_dirs()
            if pipelexpath_dirs is not None:
                self.pipelex_hub.set_default_library_dirs(pipelexpath_dirs)

        self.pipeline_manager = pipeline_manager or PipelineManager()
        self.pipelex_hub.set_pipeline_manager(pipeline_manager=self.pipeline_manager)
        self.pipeline_manager.setup()

        self.class_registry.register_classes(CoreRegistryModels.get_all_models())
        if runtime_manager.is_unit_testing:
            log.verbose("Registering test models for unit testing")
            self.class_registry.register_classes(TestRegistryModels.get_all_models())

        # --- Observers -------------------------------------------------------------------------

        if not observers:
            no_op_observer = ObserverNoOp()
            observer_telemetry = ObserverTelemetry(telemetry_manager=self.telemetry_manager)
            observers = {"noop": no_op_observer, "telemetry": observer_telemetry}
        multi_observer = MultiObserver(observers=observers)
        self.pipelex_hub.set_observer(observer=multi_observer)

        # --- Temporal --------------------------------------------------------------------------

        if get_config().temporal.is_enabled:
            from pipelex.temporal.tasks import Tasks  # noqa: PLC0415
            from pipelex.temporal.temporal_hub import temporal_hub  # noqa: PLC0415
            from pipelex.temporal.temporal_task_manager import TemporalTaskManager  # noqa: PLC0415

            temporal_task_manager = TemporalTaskManager()
            temporal_hub.set_task_manager(temporal_task_manager)
            temporal_task_manager.complement_catalog(
                extra_catalog=Tasks.TASK_PACKS,
                extra_workflows=[],
                extra_activities=[],
            )
            temporal_task_manager.setup()
            self._temporal_task_manager = temporal_task_manager

        # --- Pipe Router -----------------------------------------------------------------------

        if pipe_router:
            self.pipelex_hub.set_pipe_router(pipe_router)
        elif get_config().temporal.is_enabled:
            from pipelex.temporal.tprl_pipe.temporal_pipe_router import make_temporal_pipe_router  # noqa: PLC0415

            self.pipelex_hub.set_pipe_router(make_temporal_pipe_router())
        else:
            self.pipelex_hub.set_pipe_router(PipeRouter(observer=multi_observer))

        # --- Pipe Run --------------------------------------------------------------------------

        if get_config().temporal.is_enabled:
            from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415

            self.pipelex_hub.set_pipe_run(make_temporal_pipe_run())
        else:
            self.pipelex_hub.set_pipe_run(PipeRun(pipe_router=self.pipelex_hub.get_required_pipe_router()))

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} setup done")

    def teardown(self):
        # temporal
        if self._temporal_task_manager is not None:
            from pipelex.temporal.temporal_hub import temporal_hub  # noqa: PLC0415
            from pipelex.temporal.temporal_task_manager import TemporalTaskManager  # noqa: PLC0415

            if isinstance(self._temporal_task_manager, TemporalTaskManager):
                self._temporal_task_manager.teardown()
            temporal_hub.reset()

        # pipelex
        self.pipeline_manager.teardown()
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
        TemplateLoader.reset()
        TemplateRegistry.clear()

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
        needs_inference: bool = True,
        temporal_enabled: bool | None = None,
        needs_model_specs: bool | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipeline_manager: PipelineManager | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        library_dirs: list[str] | list[Path] | None = None,
        config_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Self:
        """Create and initialize a Pipelex singleton instance.

        All parameters are optional dependency injections. If None, default implementations
        are used during setup. This enables customization of core components like secrets
        management, storage, model routing, and pipeline execution.

        Args:
            integration_mode: Integration mode (CLI, FASTAPI, DOCKER, MCP, N8N, PYTHON, PYTEST)
            needs_inference: When False, disables inference functionality by using a mock
                content generator and loading backends leniently (skipping those with missing
                credentials). This skips gateway terms check and model deck validation.
                Useful for commands like validate/show that don't call inference APIs.
            temporal_enabled: When provided, overrides the temporal.is_enabled config value.
                True forces Temporal workflow execution, False forces direct execution.
            needs_model_specs: When True, load real model specs even if needs_inference
                is False. When None (default), follows needs_inference. Useful for validate
                commands that need gateway-provided model specs without enabling full inference.
            class_registry: Custom class registry for dynamic loading
            secrets_provider: Custom secrets/credentials provider
            storage_provider: Custom storage backend
            models_manager: Custom model configuration manager
            inference_manager: Custom inference routing manager
            content_generator: Custom content generation implementation
            pipeline_manager: Custom pipeline management
            pipe_router: Custom pipe routing logic
            reporting_delegate: Custom reporting handler
            telemetry_config: Custom telemetry configuration
            telemetry_manager: Custom telemetry manager
            observers: Custom observers for pipeline events
            library_dirs: Default library directories for pipeline execution. If provided, these
                directories will be used instead of the PIPELEXPATH environment variable.
                Per-call library_dirs in execute/start will override this default.
            config_overrides: Optional dict deep-merged on top of all TOML config layers
                as the highest-priority override. Useful for tests that need specific
                config without editing TOML files.
            **kwargs: Additional configuration options, only supported by your own subclass of Pipelex if you really need one

        Returns:
            Initialized Pipelex instance.

        Raises:
            PipelexSetupError: If Pipelex is already initialized or setup fails

        """
        if cls.get_optional_instance() is not None:
            msg = "Pipelex is already initialized"
            raise PipelexSetupError(msg)

        pipelex_instance = cls(config_overrides=config_overrides)
        try:
            pipelex_instance.setup(
                integration_mode=integration_mode,
                needs_inference=needs_inference,
                temporal_enabled=temporal_enabled,
                needs_model_specs=needs_model_specs,
                class_registry=class_registry,
                secrets_provider=secrets_provider,
                storage_provider=storage_provider,
                models_manager=models_manager,
                inference_manager=inference_manager,
                content_generator=content_generator,
                pipeline_manager=pipeline_manager,
                pipe_router=pipe_router,
                reporting_delegate=reporting_delegate,
                telemetry_config=telemetry_config,
                telemetry_manager=telemetry_manager,
                observers=observers,
                library_dirs=library_dirs,
                **kwargs,
            )
            if needs_inference:
                pipelex_instance.models_manager.validate_model_deck()
        except BaseException:
            # Cleanup the singleton instance if setup fails to avoid "already initialized" errors.
            if cls in MetaSingleton.instances:
                del MetaSingleton.instances[cls]
            raise
        # Publish readiness only now: setup() AND the optional validate_model_deck() have both succeeded
        # and the delete-on-failure handler above is behind us, so a reader can never adopt an instance
        # that is about to be removed from the registry.
        pipelex_instance.is_ready = True
        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} ready")
        return pipelex_instance

    @classmethod
    def get_optional_instance(cls) -> Self | None:
        instance = MetaSingleton.instances.get(cls)
        return cast("Self | None", instance)

    @classmethod
    def is_fully_booted(cls) -> bool:
        """True only when a singleton exists AND has completed make() (setup + validation).

        Distinct from ``get_optional_instance() is not None``: the metaclass registers the instance
        before ``setup()`` configures the hub. Callers that must not touch a half-built instance
        (``ensure_pipelex_booted``) gate on this.
        """
        instance = cls.get_optional_instance()
        return instance is not None and instance.is_ready

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
