"""The kernel layer's composition root: stand up inference without the method interpreter.

Pipelex has two layers and one hub each (``docs/contribute/hub-layering.md``). Every package in the
tree is placed on one side of that line and pinned there, but the *composition root* was the one
module that never got the treatment: a single class that booted both layers in one interleaved
sequence, so the only way into the process constructed an ``InterpreterHub``, a ``LibraryManager``, a
``PipelineManager``, a ``PipeRouter`` and a ``PipeRun`` whether the caller would ever load a method or
not. The layering property was real for *importing* and vacuous for *booting*.

This module is the kernel half. It stands up config, logging, secrets, telemetry, the class and func
registries, the template sets, the model deck, storage, the content generator, the inference manager,
the reporting delegate and the observers — everything present at execution time whatever is loaded —
and it loads **zero interpreter modules** doing it. ``pipelex.pipelex.Pipelex`` is the interpreter half:
it subclasses this class, imports it downward (which the interpreter layer may do) and appends the
method machinery.

The split is the same move the built-in plugin manifests made, and it is what finally gives
``KERNEL_BUILTIN_PLUGINS`` a caller: a kernel-only boot discovers exactly that half, so the
``direct`` orchestrator, the direct bundle validator and the built-in PipeFunc executor modes — all
interpreter-contributed — are simply absent. Nothing here resolves out of those registries at boot;
they are looked up at run time, by the interpreter.

**Every import in this module stays at module top level.** That is not incidental: a function-local
import is precisely what hides a breach from the static guard and the import-closure test at the same
time, so if one ever seems necessary here the placement is wrong and the type should move instead.
The module is declared in the hub-layering guard's ``KERNEL_LAYER_PACKAGES`` and listed in the
closure test's ``KERNEL_LAYER_ENTRY_POINTS``; a booted-kernel test pins the same property through
``make()`` rather than through an import.

Three ``runtime_*`` names still live at the top of the package and they are different things:
``runtime_hub`` is the kernel layer's service container, ``runtime_bridge`` is a transport, and
``runtime_boot`` — this module — is the kernel layer's composition root. Two of the three are named
after the layer under its former name; only ``runtime_bridge`` means "runtime" in the
orchestration-venue sense and keeps the word for good.
"""

import types
import warnings
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from kajson.class_registry import ClassRegistry
from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager

from pipelex import log
from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import (
    ContentGeneratorProtocol,
)
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.exceptions import (
    InferenceBackendCredentialsError,
    InferenceBackendLibraryError,
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
from pipelex.core.validation import raise_config_setup_error, report_config_refusal
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
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import RuntimeHub, set_runtime_hub
from pipelex.system.configuration.config_loader import CONFIG_REFUSED, config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.configuration.config_surface import INFERENCE_BACKEND_CONFIG_SURFACE_ID, PIPELEX_CONFIG_SURFACE_ID
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
    from pipelex.plugins.plugin_group import PluginGroup
    from pipelex.system.pipelex_service.remote_config import RemoteConfig
    from pipelex.system.pipelex_service.types import RemoteConfigSource

PACKAGE_NAME, PACKAGE_VERSION = get_package_info()

_HubSlotImplT = TypeVar("_HubSlotImplT")


BACKEND_LIBRARY_REFUSED: tuple[type[Exception], ...] = (
    InferenceBackendLibraryValidationError,
    InferenceBackendLibraryError,
)
"""Every way the inference backend library can report that its files are not loadable.

Spelled once, and beside `BootComponent` for the same reason that enum exists: what the boot does
with a refusal — name the surface, scan the ledger, drop the start-over tail — is only reachable if
the `except` clause names the class the loader really raises, and a clause that names one class of a
family is a silent hole rather than an error. `InferenceBackendLibraryError` is the one that matters
in practice: it is what the model-spec build raises for an `extra_forbidden` merge and for a
per-model key rejected by name, and it is what boot tolerance re-raises when the ledger cannot
explain the file. It escaped `setup` uncaught until this constant, so the scan could never run for
the one late component that has a ledger. `…ValidationError` is its sibling for the library index
file, `backends.toml`: a backend table whose own fields fail the blueprint — and until it was raised
there, that refusal left the loader as pydantic's bare error, which no clause here named either.
Neither has subclasses, and no other class the chain handles descends from either, so this clause
shadows nothing — `tests/unit/pipelex/test_runtime_boot_stale_backend_error.py` pins both halves
against a refusal the real loader produced.
"""


class BootComponent(StrEnum):
    """A library whose files can refuse to load after the main configuration is already up.

    The value is how the boot names the component to a user, and the member is what decides whether
    its files belong to a migration surface. Pairing the two here rather than at each `except`
    clause is deliberate: the surface is the difference between telling a user their files are
    *old* and telling them only that they are *wrong*, and a call site passing a bare name is a
    call site that can silently drop it.
    """

    ROUTING_PROFILE_LIBRARY = "routing profile library"
    INFERENCE_BACKEND_LIBRARY = "inference backend library"
    MODEL_DECK = "model deck"

    @property
    def migration_surface_id(self) -> str | None:
        """The migration surface that claims this component's files, or `None` when none does.

        Only the inference backend definitions are one. The model deck is the case worth naming:
        it is package-managed content rather than a schema, so it has a content sync and no
        ledger, and offering it `pipelex migrate` would send a user to a command with nothing to
        do. Routing profiles have neither mechanism.
        """
        match self:
            case BootComponent.INFERENCE_BACKEND_LIBRARY:
                return INFERENCE_BACKEND_CONFIG_SURFACE_ID
            case BootComponent.ROUTING_PROFILE_LIBRARY | BootComponent.MODEL_DECK:
                return None


class RuntimeBoot(metaclass=MetaSingleton):
    """Boot the kernel layer: inference, storage, models, telemetry — no method interpreter.

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
        # The process globals are single-owner, so exactly one boot may exist. Note *why* that needs a
        # guard rather than falling out of the code: the three fail in three different ways and only one
        # of them is loud. ``log.configure`` refuses a second call. ``set_runtime_hub`` overwrites
        # unconditionally, leaving the *first* boot running against a hub nothing else resolves to.
        # ``KajsonManager`` does the opposite and is the easiest to get backwards: it is a singleton, so
        # ``KajsonManager(class_registry=…)`` hands back the existing manager and silently discards the
        # fresh registry — the *second* boot then serves the first one's half-populated class registry
        # while its own ``self.class_registry`` is what nothing resolves to.
        #
        # Checked here *as well as* in ``make()`` — see the guard's docstring for why neither site covers
        # the other's case. Here it catches a direct construction, which is where the damage would be
        # done: ``set_runtime_hub`` below overwrites ``RuntimeHub._instance`` unconditionally, so a direct
        # construction while another boot is live would orphan that boot from the global hub and only then
        # fail, at ``log.configure``.
        self.raise_if_a_boot_already_holds_the_process_globals()

        self.is_ready: bool = False
        # ``config_dir`` is deliberately not stored on the instance. Its predecessor
        # (``self.config_dir_path``) was, and nothing ever read it, which is precisely how it came to be
        # dropped on the floor instead of reaching ``setup_config``. Keeping a copy beside the parameter
        # that is actually authoritative would re-create that trap for the next reader.
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
        except CONFIG_REFUSED as config_error:
            # Both halves of the pair, and the reason is that this arm used to catch only
            # pydantic's: `PipelexConfig` is a `ConfigRoot`, whose custom `__init__` translates
            # into `ConfigValidationError`, so the arm never fired for the one configuration
            # everything depends on and every boot failure arrived as a bare traceback instead.
            raise_config_setup_error(
                config_error=config_error,
                surface_id=PIPELEX_CONFIG_SURFACE_ID,
                config_dirs=[config_dir] if config_dir is not None else None,
            )

        log_config = get_config().runtime.log
        self.runtime_hub.set_console_print_target(target=log_config.console_print_target)
        log.configure(log_config=log_config)
        log.verbose("Logs are configured")
        if (stale_warning := config_manager.take_stale_configuration_warning()) is not None:
            log.warning(stale_warning)

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
    def _get_config_file_not_found_error_msg(*, component: BootComponent) -> str:
        """Generate error message for missing config files."""
        return f"Config files are missing for the {component}. Run `pipelex init config` to generate the missing files."

    @staticmethod
    def _get_validation_error_msg(*, component: BootComponent, validation_exc: Exception) -> str:
        """Generate error message for invalid config files.

        A component whose files belong to a migration surface gets the same treatment the loaders
        reporting through `raise_config_setup_error` get: the refusal is scanned against that
        surface's ledger, so a user whose files are merely behind is told so instead of being left
        with the model's refusal alone.

        **The refusal's own message is the body, and that is the whole reason this goes through
        `report_config_refusal`.** Every loader behind these components says *where* before it says
        what — model, backend and file, or the deck's paths — and then quotes the pydantic analysis;
        a builder that reached through to the pydantic error and translated only that kept the half
        a reader can least act on. It also could not handle the second shape a backend file refuses
        in: a per-model key rejected by name for not being header-shaped carries no pydantic error at
        all, and the old builder offered it no block on its way to saying `Unexpexted error:None`.

        > **The block names every root `pipelex migrate` walks, which can be more than the one the
        > loader read.** `backends_dir_path` resolves to a single directory (a project's `.pipelex/`
        > wins the whole directory over the global one) while the remedy walks both, and the block
        > describes what the remedy would do. Narrowing it to the directory the loader used would
        > need the path off the concrete `ModelManager`, which `ModelManagerAbstract` — a public
        > injection point — deliberately does not expose; see the note at the `models_manager.setup`
        > call below.

        Args:
            component: What refused — the message names it, and it carries the surface.
            validation_exc: The refusal, whose own message is the body of what the user reads.

        Returns:
            The message, carrying the migration paragraph when the scan found one.
        """
        report = report_config_refusal(refusal=validation_exc, surface_id=component.migration_surface_id)
        if report.migration is not None:
            # Regeneration is never offered beside a migration: the block has just promised that
            # `pipelex migrate` keeps every value the file holds, and `pipelex init config` is
            # described in the next breath as resetting them. Whichever a user followed, the other
            # sentence made it the wrong choice.
            return f"""
{report.message}

Config files are invalid for the {component}.
If you need help, drop by our Discord: we're happy to assist: {URLs.discord}.
"""
        return f"""
{report.message}

Config files are invalid for the {component}.
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
        entry_point_groups: "Sequence[PluginGroup] | None" = None,
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
    ) -> None:
        """Stand up the kernel layer.

        ``builtin_plugins`` defaults to ``KERNEL_BUILTIN_PLUGINS`` — the kernel-layer half — so a bare
        kernel boot never loads the interpreter-touching built-ins; the interpreter boot passes the
        composed list instead. ``core_unconditional_plugin_names`` defaults to the kernel-layer half for
        the same reason, and must describe the same set as ``builtin_plugins``: requiring a name that was
        never discovered fails boot. ``entry_point_groups`` is the same story for *installed* plugins and
        defaults to ``KERNEL_ENTRY_POINT_GROUPS``: a bare kernel boot never even queries the interpreter
        group, so no interpreter-side plugin module is imported into the process.

        Every other argument is the kernel subset of the same injections ``Pipelex.make`` documents.
        """
        if kwargs:
            msg = f"The base setup method does not support any additional arguments: {kwargs}"
            raise PipelexSetupError(msg)

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
            boot_orchestrator=boot_orchestrator,
            builtin_plugins=KERNEL_BUILTIN_PLUGINS if builtin_plugins is None else builtin_plugins,
            core_unconditional_plugin_names=(
                KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES if core_unconditional_plugin_names is None else core_unconditional_plugin_names
            ),
            entry_point_groups=KERNEL_ENTRY_POINT_GROUPS if entry_point_groups is None else entry_point_groups,
        )
        self._plugin_registrar = plugin_registrar
        # Reject an unknown boot orchestrator before falling through to the core defaults. The requested
        # name (CLI --orchestrator / setup(boot_orchestrator=...)) is matched against registered
        # plugin names — the same namespace the slot-claim gate uses (boot_orchestrator == plugin.name).
        # When no plugin of that name registered (not installed, disabled, or a typo) nothing claims the
        # hub slots, so without this guard the run would silently execute in-process instead of under the
        # requested runtime. Checked here to fail fast, before the telemetry/model work.
        #
        # On a kernel-only boot this rejects an interpreter-side orchestrator from either source, and for
        # the same reason in both cases: the name was never registered, so it cannot satisfy the check.
        # A built-in one is absent because ``builtin_plugins`` defaults to the kernel half; an *external*
        # one is absent because ``entry_point_groups`` defaults to ``KERNEL_ENTRY_POINT_GROUPS``, so its
        # group is never even queried. The result is a loud ``UnknownBootOrchestratorError`` rather than
        # the half-application this comment used to defer — a boot that applied the kernel slot claims
        # while silently never applying the interpreter ones (``PIPE_ROUTER`` / ``PIPE_RUN`` /
        # ``PIPE_FUNC_EXECUTOR``, all applied in ``Pipelex.setup``). What closed it is the entry-point
        # group split: the layer signal that remedy needed is now carried by the plugin's own
        # declaration.
        if boot_orchestrator is not None and boot_orchestrator not in plugin_registrar.registered_plugin_names:
            raise UnknownBootOrchestratorError(requested=boot_orchestrator)

        # Secrets provider precedence: explicit setup() param > config-selected registry factory.
        # The built-in SecretsPlugin supplies the "env" method, so there is no separate core default.
        # Resolved here because the telemetry factory just below (and the model setup further down) consume it.
        secrets_provider_registry = SecretsProviderRegistry(plugin_registrar.secrets_providers)
        self.runtime_hub.set_secrets_provider_registry(secrets_provider_registry)
        if secrets_provider is None:
            secrets_config = get_config().runtime.secrets
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
            # NOTE: ``config_dir`` scopes the main TOML load only; the inference files (backends,
            # routing profiles, model deck) still resolve through the layered ``config_manager.*``
            # properties, because pinning them requires the path overrides that exist on the *concrete*
            # ``ModelManager`` and not on ``ModelManagerAbstract`` — which is what this attribute is
            # typed as, and which is a public injection point. Widening that interface is a decision of
            # its own, so the gap is documented rather than half-closed. The docstrings say exactly
            # this; do not read ``config_dir`` as "only this directory is read" for inference.
            self.models_manager.setup(
                secrets_provider=secrets_provider,
                gateway_config=gateway_config,
                gateway_config_source=gateway_config_source,
                needs_inference=needs_inference,
            )
        except RoutingProfileLibraryNotFoundError as routing_not_found_exc:
            msg = self._get_config_file_not_found_error_msg(component=BootComponent.ROUTING_PROFILE_LIBRARY)
            raise PipelexSetupError(msg) from routing_not_found_exc
        except InferenceBackendLibraryNotFoundError as backend_not_found_exc:
            msg = self._get_config_file_not_found_error_msg(component=BootComponent.INFERENCE_BACKEND_LIBRARY)
            raise PipelexSetupError(msg) from backend_not_found_exc
        except ModelDeckNotFoundError as deck_not_found_exc:
            msg = self._get_config_file_not_found_error_msg(component=BootComponent.MODEL_DECK)
            raise PipelexSetupError(msg) from deck_not_found_exc
        except RoutingProfileDisabledBackendError as routing_profile_exc:
            msg = f"Some backend(s) required for a routing profile is not enabled: {routing_profile_exc}"
            raise PipelexSetupError(msg) from routing_profile_exc

        except BACKEND_LIBRARY_REFUSED as backend_validation_exc:
            msg = self._get_validation_error_msg(component=BootComponent.INFERENCE_BACKEND_LIBRARY, validation_exc=backend_validation_exc)
            raise PipelexSetupError(msg) from backend_validation_exc
        except ModelDeckValidationError as deck_validation_exc:
            msg = self._get_validation_error_msg(component=BootComponent.MODEL_DECK, validation_exc=deck_validation_exc)
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

        # --- Plugin-derived registries --------------------------------------------------------
        # The plugin registrar was built earlier (with the boot-orchestrator gate checked and the
        # config-selected secrets provider resolved) just before the telemetry factory. Turn its
        # accumulated contributions into the hub registries here — after the gateway/model setup checks
        # and before the hub setup points below — the family worker factories look their backends up on
        # these at run time.
        #
        # The orchestrator and bundle-validator registries are interpreter-contributed and therefore
        # empty on a kernel-only boot. That is fine and deliberate: nothing here resolves out of them,
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
            storage_config = get_config().runtime.storage
            storage_provider = storage_provider_registry.get_required(method=storage_config.method)(storage_config)
        self.runtime_hub.set_storage_provider(storage_provider)

        # Keyless boot forces every run to DRY — applied at runtime_hub.resolve_run_mode_for_boot,
        # which every run-params factory calls (the pipe tier's PipeRunParamsFactory.make_run_params
        # and the kernel tier's PipelexKernel.make), covering every entry point; generator selection is
        # backend-keyed unconditionally (eng review D4) — a keyless Temporal submitter must still
        # dispatch activities and mock inside them, so `needs_inference` plays no role in picking the
        # generator. Its other boot roles (gateway/model setup, credentials, telemetry) are unchanged.
        self.runtime_hub.set_dry_run_forced(is_forced=not needs_inference)
        # The orchestrator plugin this process booted under, recorded as boot-scoped hub state rather
        # than written into the config object — nothing in a pipelex.toml names an orchestrator, and
        # routing a boot argument through the config would make it look settable. The slot-claim *gate*
        # does not read this: a plugin's register() matched `registrar.boot_orchestrator` back at
        # discovery, and the unknown-name guard above reads the argument. What reads it is run-time
        # code asking whether it owns the process, so it must be set before the thunks below run.
        self.runtime_hub.set_boot_orchestrator(boot_orchestrator=boot_orchestrator)
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
        # Built from kernel-layer parts and held on the instance because the interpreter half's
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

        **Best-effort, per callback.** Each is unbounded third-party code, and a failure in one must not
        skip the rest: with two plugins registered, a raising first callback would otherwise leave the
        second plugin's runtime live. Catching around the *loop* instead of inside it looks equivalent
        and is not — the loop has already exited by then. Errors are logged rather than propagated,
        because no caller of a teardown can act on "plugin B failed to release", whereas every caller is
        harmed by B never being asked. Same shape as ``TelemetryManager.teardown``, which wraps each of
        its own shutdown steps for the same reason.
        """
        if self._plugin_registrar is None:
            return
        for teardown_callback in reversed(self._plugin_registrar.teardown_callbacks):
            try:
                teardown_callback()
            except Exception as teardown_exc:  # ruff: ignore[blind-except]
                # (2) a plugin-registered callback is unbounded third-party code; its exception surface
                # cannot be enumerated, and the remaining callbacks still have resources to release.
                log.error(f"A plugin teardown callback failed and was skipped: {teardown_exc}")

    def _teardown_runtime(self) -> None:
        """Release what the runtime boot acquired, and the process-global *state* with it.

        Not the hub *instances*: ``set_runtime_hub`` (and, on the interpreter half,
        ``set_interpreter_hub``) overwrite a ``ClassVar`` with no reset counterpart, so after this runs
        ``get_runtime_hub()`` still hands out the torn-down hub rather than raising "not initialized".
        Harmless in practice — the next boot replaces it — but worth not claiming otherwise.

        The releases in the ``finally`` are what make the process *re-bootable*, so they must not be
        skipped by a raising step above them — and several of those steps are reached through an
        injectable abstract type (``telemetry_manager``, ``reporting_delegate``, ``class_registry`` are
        all public ``make()`` injection points), so the built-in implementations' "teardown never
        raises" guarantee does not cover them. Unguarded, a raiser would strand this instance in
        ``MetaSingleton.instances`` and leave the process **permanently** unbootable: the next ``make()``
        dies on "already initialized", and ``teardown_if_needed`` cannot rescue it because it resolves
        the same instance and re-enters the same raiser. ``finally`` and no ``except``: the failure still
        propagates — a teardown that half-failed must not look successful.

        What a raising step *does* still skip is the releases that follow it in the ``try`` — the ones
        before it have already run. That set is now only the *dangling* half: an SDK client left open, a
        reporting buffer unflushed, the previous boot's ``func_registry`` entries carried forward.
        Everything that would instead **poison** the next boot moved into the ``finally``, so the two
        release paths guarantee the same set. Closing the dangling half means collapsing this path and
        ``_release_after_failed_boot`` into one list.
        """
        try:
            if self.telemetry_manager:
                self.telemetry_manager.teardown()

            # cogt
            self.inference_manager.teardown()
            if self.reporting_delegate:
                self.reporting_delegate.teardown()
            self.sdk_client_manager.teardown()

            # tools
            if self.class_registry:
                self.class_registry.teardown()
            func_registry.teardown()

            log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} teardown done (except config & logs)")
        finally:
            # The runtime hub releases its process-global config and boot-scoped flags. ``class_registry_scoping``
            # is reset here
            # too: the interpreter half installs the resolver at boot, so releasing it belongs to whichever
            # teardown runs — and on a kernel-only boot nothing installed it, where the reset is a no-op.
            self.runtime_hub.reset_boot_state()
            class_registry_scoping.reset()
            # The same three ``_release_after_failed_boot`` releases, deliberately kept identical: these are
            # the ones that *poison* the next boot rather than merely dangle, so they must not sit above a
            # step that can raise. ``KajsonManager`` is the sharp one, and it is easy to get backwards — it
            # is a singleton, so a surviving manager makes the next boot's ``KajsonManager(class_registry=…)``
            # hand back the old one and silently discard the fresh registry. ``get_class_registry()`` would
            # then serve the previous boot's contents while the new boot's own registrations land somewhere
            # nothing resolves to, and that boot would still report ``is_ready``. Leaving these in the
            # ``try`` traded the old *loud* failure — "already initialized", because a raiser skipped the
            # de-registration below as well — for precisely that silent one. All three are idempotent.
            KajsonManager.teardown()
            TemplateLoader.reset()
            TemplateRegistry.clear()
            # Clear the singleton instance from metaclass
            if self.__class__ in MetaSingleton.instances:
                del MetaSingleton.instances[self.__class__]

    def teardown(self) -> None:
        # ``try``/``finally`` and not a bare sequence, for the reason ``_release_after_failed_boot``
        # spells out at its own call to this method: ``_teardown_plugin_callbacks`` swallows each
        # callback's ordinary ``Exception``, but ``except Exception`` does not cover ``BaseException`` —
        # a plugin callback that calls ``sys.exit()``, or a ``KeyboardInterrupt`` landing mid-teardown,
        # would otherwise skip ``_teardown_runtime`` and leave this instance registered with no way back.
        # No ``except``: the failure still propagates.
        try:
            self._teardown_plugin_callbacks()
        finally:
            self._teardown_runtime()

    def _release_after_failed_boot(self) -> None:
        """Release the process globals a partial boot acquired. Called from every ``make()``'s handler.

        Covers a failure in ``setup()`` only. Both ``make()``s construct *outside* their ``try``, so a
        raise inside ``__init__`` itself — ``log.configure`` hitting "LogConfig is already set" because
        an embedding host configured pipelex logging first is the realistic one — never reaches this
        handler, and leaves nothing in ``MetaSingleton`` for ``teardown_if_needed`` to find either.
        Widening the ``try`` is not the fix: this method reads attributes ``__init__`` assigns, so it
        would fault on a half-constructed instance and hide the original error.

        A failed boot must release the process-global singletons it acquired, not just the singleton
        registration — otherwise they leak and poison the next boot in the same process. ``setup()``
        establishes these progressively (logging + hub config in ``__init__``, the ``KajsonManager``
        class registry, the template registries) and sets boot-scoped hub state (e.g. the boot
        orchestrator); failing partway skips ``teardown()``, the normal release point.

        It exists rather than calling ``teardown()`` because that path reads ``self.inference_manager``
        (and, on the interpreter half, ``self.pipeline_manager``) unguarded, and both are assigned
        partway through ``setup()``, so a half-built ``teardown()`` raises ``AttributeError``. That is
        deliberate: guarding them would let a half-built teardown look successful.

        It releases a **subset** of what ``teardown()`` does, and the subset is chosen: everything that
        would otherwise *poison the next boot* is here — the hub config and its boot-scoped flags, the class-registry scoping, the
        ``KajsonManager``, the template registries, the telemetry singleton and the ``MetaSingleton``
        registration. What is deliberately absent is ``sdk_client_manager``, ``reporting_delegate``,
        ``func_registry``, ``inference_manager`` and ``class_registry``. The first three leave resources
        dangling rather than corrupting the next boot; the last two are the very attributes a partial
        ``setup()`` may not have assigned, which is the reason this path exists at all. Adding any of
        them here would widen a second hand-maintained copy of the teardown list that is bound to
        drift from the real one. Collapsing the two paths is the right fix and is a lifecycle decision of
        its own.

        Without this, the next boot raises "LogConfig is already set" and serves a stale, half-populated
        class registry (the ``KajsonManager`` singleton ignores a fresh registry once created).

        The plugin teardown callbacks run **first**, mirroring the ordering of the normal ``teardown``,
        and they are what makes this path release more than the process-global state released below: by
        the time the interpreter tail runs, a boot-orchestrator plugin's ``TASK_MANAGER`` thunk has
        already stood its runtime up, and only the plugin knows what that cost. Our Temporal plugin's
        thunk registers its own process-global singletons and installs a sandbox predicate — it does not
        yet start a poller, which is a property of that thunk today and not of the slot. A failure
        anywhere after that thunk — the ``interpreter.pipe_func.execution_mode`` lookup raising on an unregistered mode is the
        most reachable one, since it is a plain config error — would otherwise leak it, because nothing
        else on this path calls the callbacks. Not a hypothetical widened by the boot split: the thunk
        used to run *after* the pipe-func executor resolution, ``pipeline_manager.setup()`` and the
        pipe-class registration, and now runs before all three.
        """
        # ``try``/``finally`` and not a bare sequence: the callbacks are plugin-supplied, so this is the
        # one line here that runs unbounded third-party code. If one raises, the releases below are what
        # the next boot in this process depends on — skipping them leaves logging configured (every later
        # boot dies on "LogConfig is already set"), the ``KajsonManager`` holding a half-populated class
        # registry, and this instance still registered as the singleton. It would also replace the
        # exception that actually killed the boot with a teardown error. The releases must therefore
        # happen on both paths, which is precisely what ``finally`` is for.
        # ``try``/``finally`` with no ``except``: the callbacks swallow their own per-callback failures
        # (see ``_teardown_plugin_callbacks``), so nothing ordinary escapes here — but ``except Exception``
        # there does not cover ``BaseException``, and this method's whole job is to leave the process
        # re-bootable. The releases below must therefore run even on a ``KeyboardInterrupt`` mid-teardown.
        # They are also what a raising callback must never skip: without them, logging stays configured
        # (every later boot dies on "LogConfig is already set") and the ``KajsonManager`` keeps a
        # half-populated class registry.
        try:
            self._teardown_plugin_callbacks()
        finally:
            # The telemetry manager is a *process-global singleton* (``ABCSingletonMeta``), not just an
            # attribute, so discarding this instance does not release it: the next boot in the process
            # would adopt the dead manager and export spans through it, because ``__init__`` never
            # re-runs for an already-registered singleton. Its ``teardown`` both flushes and calls
            # ``clear_instance()``.
            #
            # Isolated in its own ``try`` for the same reason the plugin callbacks are, and it is worth
            # being precise about why the obvious argument fails: the *built-in* ``TelemetryManager`` is
            # written to never raise ("telemetry teardown must never break the app"), but
            # ``telemetry_manager`` is a public ``make()`` injection point typed only as
            # ``TelemetryManagerAbstract``, so an injected implementation carries no such guarantee.
            # Unisolated, a raising one would skip every release below it — leaving logging configured
            # and the class registry half-populated — and replace the boot error on the way out. Reasoning
            # from the concrete class's guarantees about a call made through an injectable abstract type
            # is the mistake to avoid here.
            if self.telemetry_manager is not None:
                try:
                    self.telemetry_manager.teardown()
                except Exception as telemetry_exc:  # ruff: ignore[blind-except]
                    # (2) an injected telemetry manager is unbounded code; its exception surface cannot
                    # be enumerated, and the releases below must happen regardless.
                    log.error(f"Telemetry teardown failed while releasing a failed boot: {telemetry_exc}")
            self.runtime_hub.reset_boot_state()
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
        """Create and initialize a kernel-layer singleton: inference, storage, models, telemetry.

        Loads no method interpreter. Use ``pipelex.pipelex.Pipelex.make`` to boot the full stack.
        See that method for the shared arguments — including ``config_dir``, which scopes the *main
        TOML* load to a single directory (and, per that docstring, not the inference file paths); the
        ones absent here (``pipe_func_executor``, ``pipeline_manager``, ``pipe_router``,
        ``library_dirs``) are interpreter-layer injections.

        Returns the initialized runtime boot instance, and raises ``PipelexSetupError`` if a boot
        already holds the process globals or if setup fails.
        """
        # Checked here and not left to ``__init__``: on a second ``make()`` for an already-registered
        # class, ``MetaSingleton`` hands back the live instance without re-running ``__init__``, so the
        # only guard that can see this case is one that runs *before* the construction.
        cls.raise_if_a_boot_already_holds_the_process_globals()

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
    def raise_if_a_boot_already_holds_the_process_globals(cls) -> None:
        """Refuse to stand up a second boot. Called from ``__init__`` **and** from every ``make()``.

        Both call sites are load-bearing, and neither subsumes the other:

        - ``__init__`` covers a **direct construction** of a class that is not yet registered — the one
          that would do real damage, since ``set_runtime_hub`` overwrites ``RuntimeHub._instance``
          unconditionally and would orphan the live boot before failing at ``log.configure``.
        - ``make()`` covers a **second call on an already-registered class**, which ``__init__`` cannot
          see: ``MetaSingleton.__call__`` returns the registered instance without re-running
          ``__init__``, so ``make()`` would sail past the guard and re-run the whole ``setup()`` on the
          live boot — silently, returning the same object, and rebinding ``inference_manager`` and
          ``reporting_delegate`` so the previous ones are dropped without ever being torn down.

        Asked of the *base* class, which is what makes a bare ``RuntimeBoot`` and a full ``Pipelex``
        exclude each other in both directions; the message names whichever one actually holds them.
        """
        existing_boot = RuntimeBoot.get_optional_instance()
        if existing_boot is not None:
            msg = f"{type(existing_boot).__name__} is already initialized"
            raise PipelexSetupError(msg)

    @classmethod
    def get_optional_instance(cls) -> Self | None:
        """The booted instance, resolved **by subclass** rather than by exact class.

        A ``Pipelex`` *is* a ``RuntimeBoot``, and it owns the same process globals
        (``set_runtime_hub``, ``KajsonManager``, ``log.configure`` are all once-per-process). Keying
        on the exact class would let ``RuntimeBoot.is_fully_booted()`` answer ``False`` while a
        ``Pipelex`` held the runtime hub — and would let ``RuntimeBoot.make()`` boot on top of a live
        ``Pipelex``, which is the direction that actually breaks: the guard asks
        ``RuntimeBoot.get_optional_instance()`` outright, and an exact-class lookup keyed on
        ``RuntimeBoot`` cannot see an instance registered under ``Pipelex``. (The mirror direction stays
        blocked either way, because a bare runtime boot *is* registered under ``RuntimeBoot``; what
        would open it is the guard asking ``cls`` instead of the base.) In-tree precedent:
        ``TelemetryManagerAbstract`` and ``GraphTracerManager`` resolve their singletons the same way.
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
        """Teardown whichever boot holds the process globals, if any.

        This is useful for cleanup in finally blocks where the instance
        may or may not have been successfully created.

        Resolved at the **base** class, symmetric with the exclusivity guard in ``__init__``. Asking
        ``cls`` instead would deadlock the process: ``Pipelex.teardown_if_needed()`` would silently
        no-op against a live bare ``RuntimeBoot`` (``get_subclass_instance(Pipelex)`` cannot see one)
        while ``Pipelex(...)`` kept refusing because one exists — with no way out. A release must be
        able to clear everything its matching guard refuses on.
        """
        instance = RuntimeBoot.get_optional_instance()
        if instance is not None:
            instance.teardown()
