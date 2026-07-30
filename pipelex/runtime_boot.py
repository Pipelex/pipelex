"""The runtime layer's composition root: stand up inference without the method interpreter.

Pipelex has two layers and one hub each (``docs/contribute/hub-layering.md``). Every package in the
tree is placed on one side of that line and pinned there, but the *composition root* was the one
module that never got the treatment: a single class that booted both layers in one interleaved
sequence, so the only way into the process constructed an ``InterpreterHub``, a ``LibraryManager``, a
``PipelineManager``, a ``PipeRouter`` and a ``PipeRun`` whether the caller would ever load a method or
not. The layering property was real for *importing* and vacuous for *booting*.

This module is the runtime half. It stands up config, logging, secrets, telemetry, the class and func
registries, the template sets, the model deck, storage, the content generator, the inference manager,
the reporting delegate and the observers — everything present at execution time whatever is loaded —
and it loads **zero interpreter modules** doing it. ``pipelex.pipelex.Pipelex`` is the interpreter half:
it subclasses this class, imports it downward (which the interpreter layer may do) and appends the
method machinery.

The split is the same move the built-in plugin manifests made, and it is what finally gives
``RUNTIME_BUILTIN_PLUGINS`` a caller: a runtime-only boot discovers exactly that half, so the
``direct`` orchestrator, the direct bundle validator and the built-in PipeFunc executor modes — all
interpreter-contributed — are simply absent. Nothing here resolves out of those registries at boot;
they are looked up at run time, by the interpreter.

**Every import in this module stays at module top level.** That is not incidental: a function-local
import is precisely what hides a breach from the static guard and the import-closure test at the same
time, so if one ever seems necessary here the placement is wrong and the type should move instead.
The module is declared in the hub-layering guard's ``RUNTIME_LAYER_PACKAGES`` and listed in the
closure test's ``RUNTIME_LAYER_ENTRY_POINTS``; a booted-runtime test pins the same property through
``make()`` rather than through an import.

Three ``runtime_*`` names now live at the top of the package and they are different things:
``runtime_hub`` is the runtime layer's service container, ``runtime_bridge`` is a transport, and
``runtime_boot`` — this module — is the runtime layer's composition root.
"""

import types
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

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
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.core.registry_models import CoreRegistryModels
from pipelex.core.stuffs.stuff_template_set import STUFF_TEMPLATE_SET
from pipelex.core.validation import report_validation_error
from pipelex.graph.mermaidflow.template_set import MERMAID_TEMPLATE_SET
from pipelex.graph.reactflow.template_set import REACTFLOW_TEMPLATE_SET
from pipelex.observer.multi_observer import MultiObserver
from pipelex.observer.observer_protocol import ObserverNoOp, ObserverProtocol
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.exceptions import UnknownBootOrchestratorError
from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry
from pipelex.plugins.model_lister_registry import ModelListerRegistry
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.plugins.registrar import HubSlot, PluginRegistrar
from pipelex.plugins.sdk_client_manager import SdkClientManager
from pipelex.plugins.secrets_provider_registry import SecretsProviderRegistry
from pipelex.plugins.storage_provider_registry import StorageProviderRegistry
from pipelex.providers.builtins import RUNTIME_BUILTIN_PLUGINS, RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import RuntimeHub, set_runtime_hub
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.configuration.configs import PipelexConfig
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
from pipelex.system.registries.class_registry_access import class_registry_scoping
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
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.urls import URLs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.plugins.contract import PipelexPlugin
    from pipelex.system.pipelex_service.remote_config import RemoteConfig
    from pipelex.system.pipelex_service.types import RemoteConfigSource

PACKAGE_NAME, PACKAGE_VERSION = get_package_info()

_HubSlotImplT = TypeVar("_HubSlotImplT")


class RuntimeBoot(metaclass=MetaSingleton):
    """Boot the runtime layer: inference, storage, models, telemetry — no method interpreter.

    Subclassed by ``pipelex.pipelex.Pipelex``, which appends the interpreter constructions. The
    singleton is therefore shared between the two: the class-level accessors below resolve **by
    subclass**, so ``RuntimeBoot.is_fully_booted()`` answers ``True`` when a ``Pipelex`` owns the
    process globals. Resolving by exact class instead would tell the embedder this module exists for
    that nothing is booted while a ``Pipelex`` held the runtime hub.
    """

    def __init__(
        self,
        *,
        config_dir: Path | None = None,
        config_cls: type[ConfigRoot] | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        # Readiness gate: flipped True only at the very end of make(), after setup() and the optional
        # validate_model_deck() both succeed. Readers (ensure_pipelex_booted) must gate on this, NOT on
        # mere registry presence -- MetaSingleton registers the instance before setup() configures the hub.
        self.is_ready: bool = False
        # ``config_dir`` is deliberately not stored on the instance. Its predecessor was
        # (``self.config_dir_path``) and nothing ever read it, which is precisely how it came to be
        # dropped on the floor instead of reaching ``setup_config``. Keeping a resolved copy beside the
        # parameter that is actually authoritative would re-create that trap for the next reader.
        # The runtime hub is process-scoped infrastructure, and it is constructed first because it is
        # the lower layer, so it reads first. The interpreter half installs its own hub afterwards;
        # that install does not need this one (it only stores the class-registry scoping resolver,
        # which resolves lazily at call time).
        self.runtime_hub = RuntimeHub()
        set_runtime_hub(self.runtime_hub)

        # tools
        try:
            self.runtime_hub.setup_config(
                config_cls=config_cls or PipelexConfig,
                config_overrides=config_overrides,
                config_dir=config_dir,
            )
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="config", validation_error=validation_error)
            msg = f"Could not setup config because of: {validation_error_msg}"
            raise PipelexConfigError(msg) from validation_error

        log_config = get_config().pipelex.log_config
        self.runtime_hub.set_console_print_target(target=log_config.console_print_target)
        log.configure(log_config=log_config)
        log.verbose("Logs are configured")

        # tools
        self.class_registry: ClassRegistryAbstract | None = None
        self.func_registry: FuncRegistry | None = None
        # plugins — the registrar is built in setup() (build_registrar); held for the slot-claim /
        # CLI-command / teardown apply-points. Declared here so teardown() can guard on it.
        self._plugin_registrar: PluginRegistrar | None = None
        # cogt
        self.sdk_client_manager = SdkClientManager()
        self.runtime_hub.set_sdk_client_manager(self.sdk_client_manager)

        self.reporting_delegate: ReportingProtocol | None = None
        self.telemetry_manager: TelemetryManagerAbstract | None = None

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} runtime init done")

    @staticmethod
    def _get_config_file_not_found_error_msg(*, component_name: str) -> str:
        """Generate error message for missing config files."""
        return f"Config files are missing for the {component_name}. Run `pipelex init config` to generate the missing files."

    @staticmethod
    def _get_validation_error_msg(*, component_name: str, validation_exc: Exception) -> str:
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
        *,
        integration_mode: IntegrationMode,
        needs_inference: bool = True,
        boot_orchestrator: str | None = None,
        needs_model_specs: bool | None = None,
        builtin_plugins: "Sequence[PipelexPlugin] | None" = None,
        core_unconditional_plugin_names: frozenset[str] | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        **kwargs: Any,
    ):
        """Stand up the runtime layer.

        ``builtin_plugins`` defaults to ``RUNTIME_BUILTIN_PLUGINS`` — the runtime-layer half — so a bare
        runtime boot never loads the interpreter-touching built-ins; the interpreter boot passes the
        composed list instead. ``core_unconditional_plugin_names`` defaults to the runtime-layer half for
        the same reason, and must describe the same set as ``builtin_plugins``: requiring a name that was
        never discovered fails boot.

        Every other argument is the runtime subset of the same injections ``Pipelex.make`` documents.
        """
        if kwargs:
            msg = f"The base setup method does not support any additional arguments: {kwargs}"
            raise PipelexSetupError(msg)

        # Boot this process under the named orchestrator plugin, when explicitly provided.
        # The matching boot-orchestrator plugin (e.g. Temporal) claims the hub slots in its
        # register() iff plugins.boot_orchestrator == its own name; any other value is in-process.
        if boot_orchestrator is not None:
            get_config().plugins.boot_orchestrator = boot_orchestrator

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

        # --- Plugin discovery -----------------------------------------------------------------
        # Build the plugin registrar from the fully-resolved config (pure and import-light:
        # registering the built-ins imports no backend SDK, constructs no client, touches no hub).
        # Built here — after the gateway service/terms precondition gate above (so an unaccepted-terms or
        # first-run boot fails fast before any discovery work) and before the telemetry factory below,
        # which is the first consumer of the secrets provider. Secrets is now a config-selected plugin
        # seam: the built-in SecretsPlugin's factory (and any external pipelex-secrets-<backend>) is
        # looked up from the registrar-derived SecretsProviderRegistry just below. The other registries
        # (inference, storage, …) are still built later at their own hub-set points, all referencing this
        # same already-built registrar; the slot-claim thunks / teardown callbacks it also accumulates are
        # applied at their ordered apply-points in later phases.
        plugin_registrar = build_registrar(
            config=get_config(),
            builtin_plugins=RUNTIME_BUILTIN_PLUGINS if builtin_plugins is None else builtin_plugins,
            core_unconditional_plugin_names=(
                RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES if core_unconditional_plugin_names is None else core_unconditional_plugin_names
            ),
        )
        self._plugin_registrar = plugin_registrar
        # Reject an unknown boot orchestrator before falling through to the core defaults. The requested
        # name (CLI --orchestrator / setup(boot_orchestrator=...) / config) is matched against registered
        # plugin names — the same namespace the slot-claim gate uses (boot_orchestrator == plugin.name).
        # When no plugin of that name registered (not installed, disabled, or a typo) nothing claims the
        # hub slots, so without this guard the run would silently execute in-process instead of under the
        # requested runtime. Checked here to fail fast, before the telemetry/model work.
        #
        # On a runtime-only boot this also rejects an interpreter-contributed orchestrator name, which is
        # correct: the requested runtime genuinely cannot be honoured by a process with no interpreter.
        requested_boot_orchestrator = get_config().plugins.boot_orchestrator
        if requested_boot_orchestrator is not None and requested_boot_orchestrator not in plugin_registrar.registered_plugin_names:
            raise UnknownBootOrchestratorError(requested=requested_boot_orchestrator)

        # Secrets provider precedence: explicit setup() param > config-selected registry factory.
        # The built-in SecretsPlugin supplies the "env" method, so there is no separate core default.
        # Resolved here because the telemetry factory just below (and the model setup further down) consume it.
        secrets_provider_registry = SecretsProviderRegistry(plugin_registrar.secrets_providers)
        self.runtime_hub.set_secrets_provider_registry(secrets_provider_registry)
        if secrets_provider is None:
            secrets_config = get_config().pipelex.secrets_config
            secrets_provider = secrets_provider_registry.get_required(method=secrets_config.method)(secrets_config)

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
        self.runtime_hub.set_telemetry_manager(telemetry_manager=self.telemetry_manager)

        # --- Tools ----------------------------------------------------------------------------

        self.class_registry = class_registry or ClassRegistry()
        self.kajson_manager = KajsonManager(class_registry=self.class_registry)

        self.func_registry = func_registry or FuncRegistry()
        self.runtime_hub.set_func_registry(func_registry=self.func_registry)
        self.runtime_hub.set_secrets_provider(secrets_provider=secrets_provider)
        # Storage is selected from the config-driven StorageProviderRegistry, built from the plugin
        # registrar (constructed above, just before the telemetry factory). Its resolution and hub-set
        # still happen later at the plugin-derived-registries block — after secrets is on the hub here,
        # so the GCP factory's secret read works.

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

        # --- AI Models and Inference Management ------------------------------------------------

        self.sdk_client_manager.setup()

        self.models_manager: ModelManagerAbstract = models_manager or ModelManager()
        self.runtime_hub.set_models_manager(models_manager=self.models_manager)

        try:
            self.models_manager.setup(
                secrets_provider=secrets_provider,
                gateway_config=gateway_config,
                gateway_config_source=gateway_config_source,
                needs_inference=needs_inference,
            )
        except RoutingProfileLibraryNotFoundError as routing_not_found_exc:
            msg = self._get_config_file_not_found_error_msg(component_name="routing profile library")
            raise PipelexSetupError(msg) from routing_not_found_exc
        except InferenceBackendLibraryNotFoundError as backend_not_found_exc:
            msg = self._get_config_file_not_found_error_msg(component_name="inference backend library")
            raise PipelexSetupError(msg) from backend_not_found_exc
        except ModelDeckNotFoundError as deck_not_found_exc:
            msg = self._get_config_file_not_found_error_msg(component_name="model deck")
            raise PipelexSetupError(msg) from deck_not_found_exc
        except RoutingProfileDisabledBackendError as routing_profile_exc:
            msg = f"Some backend(s) required for a routing profile is not enabled: {routing_profile_exc}"
            raise PipelexSetupError(msg) from routing_profile_exc

        except InferenceBackendLibraryValidationError as backend_validation_exc:
            msg = self._get_validation_error_msg(component_name="inference backend library", validation_exc=backend_validation_exc)
            raise PipelexSetupError(msg) from backend_validation_exc
        except ModelDeckValidationError as deck_validation_exc:
            msg = self._get_validation_error_msg(component_name="model deck", validation_exc=deck_validation_exc)
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

        # Keyless boot forces every run to DRY — consumed at PipeRunParamsFactory.make_run_params,
        # the single writer of run_mode, covering every entry point; generator selection is
        # backend-keyed unconditionally (eng review D4) — a keyless Temporal submitter must still
        # dispatch activities and mock inside them, so `needs_inference` plays no role in picking the
        # generator. Its other boot roles (gateway/model setup, credentials, telemetry) are unchanged.
        # --- Plugin-derived registries --------------------------------------------------------
        # The plugin registrar was built earlier (with the boot-orchestrator gate checked and the
        # config-selected secrets provider resolved) just before the telemetry factory. Turn its
        # accumulated contributions into the hub registries here — after the gateway/model setup checks
        # and before the hub setup points below — the family worker factories look their backends up on
        # these at run time.
        #
        # The orchestrator and bundle-validator registries are interpreter-contributed and therefore
        # empty on a runtime-only boot. That is fine and deliberate: nothing here resolves out of them,
        # they are looked up at run time by the interpreter.
        self.runtime_hub.set_inference_backend_registry(InferenceBackendRegistry(plugin_registrar.inference_backends))
        self.runtime_hub.set_model_lister_registry(ModelListerRegistry(plugin_registrar.model_listers))
        self.runtime_hub.set_orchestrator_registry(OrchestratorRegistry(plugin_registrar.orchestrators))
        self.runtime_hub.set_bundle_validator_registry(BundleValidatorRegistry(plugin_registrar.bundle_validators))
        storage_provider_registry = StorageProviderRegistry(plugin_registrar.storage_providers)
        self.runtime_hub.set_storage_provider_registry(storage_provider_registry)
        # Storage provider precedence: explicit setup() param > config-selected registry factory.
        # The built-in StoragePlugin supplies every method, so there is no separate core default.
        # Resolves here (after secrets is on the hub) so the GCP factory's secret read works.
        if storage_provider is None:
            storage_config = get_config().pipelex.storage_config
            storage_provider = storage_provider_registry.get_required(method=storage_config.method)(storage_config)
        self.runtime_hub.set_storage_provider(storage_provider)

        self.runtime_hub.set_dry_run_forced(is_forced=not needs_inference)
        # Injection precedence (codex C8): explicit setup() param > plugin slot-claim thunk > core default.
        # A boot-orchestrator plugin (Temporal worker) claims the CONTENT_GENERATOR slot; its thunk runs
        # only here, never at register, so booting a non-worker process imports no host-runtime SDK.
        if content_generator is None:
            content_generator = self._resolve_hub_slot(
                slot=HubSlot.CONTENT_GENERATOR,
                default=lambda: ContentGenerator(generated_content_factory=GeneratedContentFactory(storage_provider=storage_provider)),
            )
        self.runtime_hub.set_content_generator(content_generator)

        self.inference_manager = inference_manager or InferenceManager()
        self.runtime_hub.set_inference_manager(self.inference_manager)

        # --- Libraries & Registries -------------------------------------------------------------

        self.reporting_delegate = reporting_delegate or ReportingManager()
        self.runtime_hub.set_report_delegate(self.reporting_delegate)
        self.reporting_delegate.setup()

        # Core's value model. The pipe kinds are the interpreter half's own registration
        # (``PipeRegistryModels``); the two manifests are disjoint by construction and pinned as such
        # by tests/unit/pipelex/test_registry_models_split.py, so which side registers first carries
        # no meaning.
        self.class_registry.register_classes(CoreRegistryModels.get_all_models())
        if runtime_manager.is_unit_testing:
            log.verbose("Registering test models for unit testing")
            self.class_registry.register_classes(TestRegistryModels.get_all_models())

        # --- Observers -------------------------------------------------------------------------
        # Built from runtime-layer parts and held on the instance because the interpreter half's
        # PipeRouter consumes it — one of the two seams that lets the interpreter constructions be a
        # tail rather than an interleaving.

        if not observers:
            no_op_observer = ObserverNoOp()
            observer_telemetry = ObserverTelemetry(telemetry_manager=self.telemetry_manager)
            observers = {"noop": no_op_observer, "telemetry": observer_telemetry}
        self.multi_observer = MultiObserver(observers=observers)

        # --- Task Manager ----------------------------------------------------------------------
        # The TASK_MANAGER slot is claimed only by a boot-orchestrator plugin running this process as
        # its runtime (a Temporal worker). The thunk does the full wiring on the plugin's own hub and
        # is torn down via a registered teardown callback (LIFO) — no core default, no explicit param.

        task_manager_factory = plugin_registrar.slot_claims.get(HubSlot.TASK_MANAGER)
        if task_manager_factory is not None:
            task_manager_factory()

        # --- Isolated-execution probe ----------------------------------------------------------
        # Claimed only by a boot-orchestrator plugin whose runtime has a replay/activity split (e.g. a
        # Temporal worker): the thunk resolves the ambient predicate that reports whether the current
        # call runs inside an isolated sub-execution (an activity). ReportingManager consults it to
        # route an activity-side usage emission to the per-process log instead of the workflow's
        # registered buffer (audit H1). Unclaimed (any in-process boot), the fresh hub's default
        # reports "never isolated", so no wiring is needed here.
        isolated_execution_probe_factory = plugin_registrar.slot_claims.get(HubSlot.ISOLATED_EXECUTION_PROBE)
        if isolated_execution_probe_factory is not None:
            self.runtime_hub.set_isolated_execution_probe(isolated_execution_probe_factory())

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} runtime setup done")

    def _resolve_hub_slot(self, *, slot: HubSlot, default: Callable[[], _HubSlotImplT]) -> _HubSlotImplT:
        """Resolve a process-global hub slot: a plugin's claimed thunk if present, else the core default.

        Call sites apply explicit-injection precedence first (an explicit ``setup()`` param wins),
        so this only arbitrates plugin-claim vs core-default. The claim is a thunk invoked here at the
        boot apply-point — never during ``register`` — so a non-worker boot constructs no plugin impl.
        The return type follows the core ``default`` (the claimed thunk is typed ``Any`` and adopts it).
        """
        if self._plugin_registrar is not None:
            factory = self._plugin_registrar.slot_claims.get(slot)
            if factory is not None:
                return cast("_HubSlotImplT", factory())
        return default()

    def _teardown_plugin_callbacks(self) -> None:
        """Run the plugin-contributed teardown callbacks, LIFO.

        Its own phase because the ordering is load-bearing: these must run *before* the interpreter
        half's ``pipeline_manager.teardown()`` so a worker's in-flight Temporal resources release
        first. ``Pipelex.teardown`` sequences the two explicitly rather than relying on a template
        hook, which is what keeps that order legible.

        Names no integration: the callbacks were registered by whichever boot-orchestrator plugin
        claimed the runtime.
        """
        if self._plugin_registrar is not None:
            for teardown_callback in reversed(self._plugin_registrar.teardown_callbacks):
                teardown_callback()

    def _teardown_runtime(self) -> None:
        """Release everything the runtime boot acquired, and the process globals with it."""
        if self.telemetry_manager:
            self.telemetry_manager.teardown()

        # cogt
        self.inference_manager.teardown()
        if self.reporting_delegate:
            self.reporting_delegate.teardown()
        self.sdk_client_manager.teardown()

        # tools
        self.kajson_manager.teardown()
        if self.class_registry:
            self.class_registry.teardown()
        func_registry.teardown()
        TemplateLoader.reset()
        TemplateRegistry.clear()

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} teardown done (except config & logs)")
        # The runtime hub releases its process-global config. ``class_registry_scoping`` is reset here
        # too: the interpreter half installs the resolver at boot, so releasing it belongs to whichever
        # teardown runs — and on a runtime-only boot nothing installed it, where the reset is a no-op.
        self.runtime_hub.reset_config()
        class_registry_scoping.reset()
        # Clear the singleton instance from metaclass
        if self.__class__ in MetaSingleton.instances:
            del MetaSingleton.instances[self.__class__]

    def teardown(self):
        self._teardown_plugin_callbacks()
        self._teardown_runtime()

    def _release_after_failed_boot(self) -> None:
        """Release the process globals a partial boot acquired. Called from every ``make()``'s handler.

        A failed boot must release the process-global singletons it acquired, not just the singleton
        registration — otherwise they leak and poison the next boot in the same process. ``setup()``
        establishes these progressively (logging + hub config in ``__init__``, the ``KajsonManager``
        class registry, the template registries) and may mutate config (e.g.
        ``plugins.boot_orchestrator``); failing partway skips ``teardown()``, the normal release point.

        This releases the same process-global state ``teardown()`` does, but only through entry points
        that are safe on a half-built instance — which is why it exists at all rather than calling
        ``teardown()``: that path reads ``self.inference_manager`` (and, on the interpreter half,
        ``self.pipeline_manager``) unguarded, and both are assigned partway through ``setup()``, so a
        half-built ``teardown()`` raises ``AttributeError``. That is deliberate: guarding them would
        let a half-built teardown look successful.

        Without this, the next boot raises "LogConfig is already set" and serves a stale, half-populated
        class registry (the ``KajsonManager`` singleton ignores a fresh registry once created).
        """
        self.runtime_hub.reset_config()
        class_registry_scoping.reset()
        KajsonManager.teardown()
        TemplateLoader.reset()
        TemplateRegistry.clear()
        # Cleanup the singleton instance if setup fails to avoid "already initialized" errors.
        if self.__class__ in MetaSingleton.instances:
            del MetaSingleton.instances[self.__class__]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> None:
        self.teardown()

    @classmethod
    def make(
        cls,
        *,
        integration_mode: IntegrationMode = IntegrationMode.PYTHON,
        needs_inference: bool = True,
        boot_orchestrator: str | None = None,
        needs_model_specs: bool | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        config_dir: Path | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> Self:
        """Create and initialize a runtime-layer singleton: inference, storage, models, telemetry.

        Loads no method interpreter. Use ``pipelex.pipelex.Pipelex.make`` to boot the full stack.
        See that method for the shared arguments — including ``config_dir``, which scopes the config
        load to a single directory; the ones absent here (``pipe_func_executor``, ``pipeline_manager``,
        ``pipe_router``, ``library_dirs``) are interpreter-layer injections.

        Returns the initialized runtime boot instance, and raises ``PipelexSetupError`` if a boot
        already holds the process globals or if setup fails.
        """
        # Asked of the *base* class, not of ``cls``: the process globals are one set, so a bare runtime
        # boot and a full ``Pipelex`` boot exclude each other in both directions. Asking ``cls`` would
        # let ``Pipelex.make()`` boot on top of a live ``RuntimeBoot`` and quietly serve its
        # half-populated class registry. The message names the class that actually holds the globals,
        # not this one: "Pipelex is already initialized" is a lie when a bare ``RuntimeBoot`` is what
        # is booted, and an embedder that never touched ``Pipelex`` deserves to be told what did.
        existing_boot = RuntimeBoot.get_optional_instance()
        if existing_boot is not None:
            msg = f"{type(existing_boot).__name__} is already initialized"
            raise PipelexSetupError(msg)

        runtime_boot = cls(config_dir=config_dir, config_overrides=config_overrides)
        try:
            runtime_boot.setup(
                integration_mode=integration_mode,
                needs_inference=needs_inference,
                boot_orchestrator=boot_orchestrator,
                needs_model_specs=needs_model_specs,
                class_registry=class_registry,
                secrets_provider=secrets_provider,
                storage_provider=storage_provider,
                models_manager=models_manager,
                inference_manager=inference_manager,
                content_generator=content_generator,
                reporting_delegate=reporting_delegate,
                telemetry_config=telemetry_config,
                telemetry_manager=telemetry_manager,
                observers=observers,
            )
            if needs_inference:
                runtime_boot.models_manager.validate_model_deck()
        except BaseException:
            runtime_boot._release_after_failed_boot()
            raise
        # Publish readiness only now: setup() AND the optional validate_model_deck() have both succeeded
        # and the delete-on-failure handler above is behind us, so a reader can never adopt an instance
        # that is about to be removed from the registry.
        runtime_boot.is_ready = True
        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} runtime ready")
        return runtime_boot

    @classmethod
    def get_optional_instance(cls) -> Self | None:
        """The booted instance, resolved **by subclass** rather than by exact class.

        A ``Pipelex`` *is* a ``RuntimeBoot``, and it owns the same process globals
        (``set_runtime_hub``, ``KajsonManager``, ``log.configure`` are all once-per-process). Keying
        on the exact class would let ``RuntimeBoot.is_fully_booted()`` answer ``False`` while a
        ``Pipelex`` held the runtime hub — and would let ``Pipelex.make()`` boot on top of a bare
        runtime boot. In-tree precedent: ``TelemetryManagerAbstract`` and ``GraphTracerManager``
        resolve their singletons the same way.
        """
        return MetaSingleton.get_subclass_instance(cls)

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
        instance = cls.get_optional_instance()
        if instance is None:
            msg = f"{cls.__name__} is not initialized"
            raise RuntimeError(msg)
        return instance

    @classmethod
    def teardown_if_needed(cls) -> None:
        """Teardown the singleton instance if it exists.

        This is useful for cleanup in finally blocks where the instance
        may or may not have been successfully created.
        """
        instance = cls.get_optional_instance()
        if instance is not None:
            instance.teardown()
