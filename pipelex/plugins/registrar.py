from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

from pydantic import BaseModel, Field

from pipelex.base_exceptions import ErrorReport
from pipelex.plugins.bundle_validator_registry import BundleValidatorProtocol
from pipelex.plugins.exceptions import (
    DuplicateBundleValidatorError,
    DuplicateHttpErrorMapperError,
    DuplicateInferenceBackendError,
    DuplicateModelListerError,
    DuplicateOrchestratorError,
    DuplicatePipeFuncExecutorError,
    DuplicateSecretsProviderError,
    DuplicateStorageProviderError,
    HubSlotAlreadyClaimedError,
)
from pipelex.plugins.inference_backend_registry import InferenceFamily, MakeWorkerFn
from pipelex.plugins.model_lister_registry import ListModelsFn
from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
from pipelex.plugins.pipe_func_executor_registry import PipeFuncExecutorFactoryFn
from pipelex.plugins.secrets_provider_registry import SecretsProviderFactoryFn
from pipelex.plugins.storage_provider_registry import StorageProviderFactoryFn
from pipelex.runtime_bridge.orchestration_mode import OrchestrationMode

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


_RegistryKeyT = TypeVar("_RegistryKeyT")
_RegistryValueT = TypeVar("_RegistryValueT")

# A plugin's framework-agnostic mapping from one transport/runtime exception to a
# structured ``ErrorReport``. A host runtime (``pipelex-api``) renders the report
# into its own HTTP error response (RFC 7807 + disclosure) — so core and the plugin
# name no web framework.
HttpErrorMapperFn = Callable[[Exception], ErrorReport]

# A thunk returning the concrete exception class a mapper applies to. The mapper is
# registered with this *provider* rather than the bare type so a plugin whose
# exception lives in a heavy orchestrator SDK (``temporalio``) can keep its
# ``register`` import-light: the provider — and any SDK import it performs to name
# the class — is invoked only when a host runtime resolves the mappers via
# ``get_http_error_mappers`` (i.e. at app construction), never at registration.
HttpErrorTypeProviderFn = Callable[[], type[Exception]]


class _HttpErrorMapperContribution(NamedTuple):
    """One plugin's deferred HTTP-error-mapper contribution.

    A ``NamedTuple`` (not a model) because it holds two callables and is never
    serialized. ``exc_type_provider`` is resolved — and any SDK import it incurs
    paid — only by ``get_http_error_mappers``, which is what keeps a contributing
    plugin's ``register`` import-light.
    """

    exc_type_provider: HttpErrorTypeProviderFn
    to_error_report: HttpErrorMapperFn
    source_plugin: str


class HubSlot(StrEnum):
    """A process-global capability slot a boot-orchestrator plugin may claim."""

    CONTENT_GENERATOR = "content_generator"
    PIPE_FUNC_EXECUTOR = "pipe_func_executor"
    PIPE_ROUTER = "pipe_router"
    PIPE_RUN = "pipe_run"
    TASK_MANAGER = "task_manager"
    ISOLATED_EXECUTION_PROBE = "isolated_execution_probe"


class PluginOrigin(StrEnum):
    BUILTIN = "builtin"
    EXTERNAL = "external"


class PluginStatus(StrEnum):
    REGISTERED = "registered"
    DISABLED = "disabled"
    BROKEN = "broken"

    @property
    def is_registered(self) -> bool:
        return self is PluginStatus.REGISTERED


class PluginDiscovery(BaseModel):
    """Observability record of one discovered plugin and what it contributed.

    Populated by ``build_registrar`` (origin/status/targets_api) and the registrar
    menu methods (one ``contributions`` line per contribution). Read by
    ``pipelex plugins list``.
    """

    name: str
    origin: PluginOrigin = Field(strict=False)
    status: PluginStatus = Field(strict=False)
    targets_api: int | None = None
    contributions: list[str] = Field(default_factory=list)
    detail: str | None = None


class PluginRegistrar:
    """The accumulator a plugin's ``register`` writes into.

    A plugin only ever calls the menu methods below. ``build_registrar`` drives
    one plugin at a time (setting the "active" discovery so contributions are
    attributed and duplicate conflicts can name both contributors), then boot
    turns the accumulated ``inference_backends`` / ``orchestrators`` into the two
    keyed registries and applies the slot-claim thunks / teardown
    callbacks at their ordered apply-points.

    All duplicate detection is fail-loud and names both contributing plugins.
    """

    def __init__(self, *, config: "PipelexConfig"):
        self.config = config
        self.inference_backends: dict[tuple[InferenceFamily, str], MakeWorkerFn] = {}
        self.model_listers: dict[str, ListModelsFn] = {}
        self.orchestrators: dict[OrchestrationMode, OrchestratorProtocol] = {}
        self.bundle_validators: dict[OrchestrationMode, BundleValidatorProtocol] = {}
        self.storage_providers: dict[str, StorageProviderFactoryFn] = {}
        self.secrets_providers: dict[str, SecretsProviderFactoryFn] = {}
        self.pipe_func_executors: dict[str, PipeFuncExecutorFactoryFn] = {}
        # Ordered list (not a type-keyed dict) because the exception types are
        # resolved lazily — only ``get_http_error_mappers`` invokes the providers,
        # so duplicate-by-type detection is deferred to resolution time too.
        self.http_error_mappers: list[_HttpErrorMapperContribution] = []
        self.slot_claims: dict[HubSlot, Callable[[], Any]] = {}
        self.teardown_callbacks: list[Callable[[], None]] = []
        self.discoveries: list[PluginDiscovery] = []
        self._inference_sources: dict[tuple[InferenceFamily, str], str] = {}
        self._model_lister_sources: dict[str, str] = {}
        self._orchestrator_sources: dict[OrchestrationMode, str] = {}
        self._bundle_validator_sources: dict[OrchestrationMode, str] = {}
        self._storage_provider_sources: dict[str, str] = {}
        self._secrets_provider_sources: dict[str, str] = {}
        self._pipe_func_executor_sources: dict[str, str] = {}
        self._slot_sources: dict[HubSlot, str] = {}
        # Reassigned per plugin by build_registrar; the floating default keeps the
        # menu methods safe to call outside a registration loop (e.g. a focused unit test).
        self._active = PluginDiscovery(name="(unregistered)", origin=PluginOrigin.BUILTIN, status=PluginStatus.REGISTERED)

    # ------------------------------------------------------------------ #
    # Driven by build_registrar (not by plugins)
    # ------------------------------------------------------------------ #

    def begin_plugin(self, *, name: str, origin: PluginOrigin, targets_api: int) -> PluginDiscovery:
        discovery = PluginDiscovery(name=name, origin=origin, status=PluginStatus.REGISTERED, targets_api=targets_api)
        self.discoveries.append(discovery)
        self._active = discovery
        return discovery

    # ------------------------------------------------------------------ #
    # Menu methods — the only surface a plugin's register() may call
    # ------------------------------------------------------------------ #

    def add_inference_backend(self, *, family: InferenceFamily, sdk: str, make_worker: MakeWorkerFn) -> None:
        self._add(
            store=self.inference_backends,
            sources=self._inference_sources,
            key=(family, sdk),
            value=make_worker,
            contribution=f"inference backend {family}:{sdk}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateInferenceBackendError(
                family=family, sdk=sdk, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_model_lister(self, *, sdk: str, lister: ListModelsFn) -> None:
        self._add(
            store=self.model_listers,
            sources=self._model_lister_sources,
            key=sdk,
            value=lister,
            contribution=f"model lister {sdk}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateModelListerError(
                sdk=sdk, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_orchestrator(self, *, mode: OrchestrationMode, orchestrator: OrchestratorProtocol) -> None:
        self._add(
            store=self.orchestrators,
            sources=self._orchestrator_sources,
            key=mode,
            value=orchestrator,
            contribution=f"orchestrator {mode}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateOrchestratorError(
                mode=mode, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_bundle_validator(self, *, mode: OrchestrationMode, validator: BundleValidatorProtocol) -> None:
        self._add(
            store=self.bundle_validators,
            sources=self._bundle_validator_sources,
            key=mode,
            value=validator,
            contribution=f"bundle validator {mode}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateBundleValidatorError(
                mode=mode, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_storage_provider(self, *, method: str, factory: StorageProviderFactoryFn) -> None:
        """Contribute a factory for one storage backend, keyed by an open ``method`` token.

        The built-in ``StoragePlugin`` registers the ``local`` / ``in_memory`` / ``s3`` / ``gcp``
        methods; an external ``pipelex-storage-<backend>`` plugin registers its own token (e.g.
        ``"azure"``). Boot reads ``storage_config.method`` and calls the looked-up factory to
        produce the one storage provider set on the hub. ``factory`` is invoked at that boot
        apply-point, never here — so a factory may do heavy work (SDK import, a hub secrets read)
        while ``register`` stays import-light. Fail-loud on a duplicate method, naming both plugins.
        """
        self._add(
            store=self.storage_providers,
            sources=self._storage_provider_sources,
            key=method,
            value=factory,
            contribution=f"storage provider {method}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateStorageProviderError(
                method=method, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_secrets_provider(self, *, method: str, factory: SecretsProviderFactoryFn) -> None:
        """Contribute a factory for one secrets backend, keyed by an open ``method`` token.

        The built-in ``SecretsPlugin`` registers the ``env`` method; an external
        ``pipelex-secrets-<backend>`` plugin registers its own token (e.g. ``"vault"``). Boot reads
        ``secrets_config.method`` and calls the looked-up factory to produce the one secrets provider
        set on the hub. ``factory`` is invoked at that boot apply-point, never here — so a factory may
        do heavy work (SDK import) while ``register`` stays import-light. Fail-loud on a duplicate
        method, naming both plugins.
        """
        self._add(
            store=self.secrets_providers,
            sources=self._secrets_provider_sources,
            key=method,
            value=factory,
            contribution=f"secrets provider {method}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateSecretsProviderError(
                method=method, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_pipe_func_executor(self, *, mode: str, factory: PipeFuncExecutorFactoryFn) -> None:
        """Contribute a factory for one PipeFunc execution mode, keyed by an open ``mode`` token.

        The built-in ``PipeFuncPlugin`` registers ``direct`` (in-process) and ``local_sandbox`` (local
        subprocess); an external sandbox plugin (``pipelex-daytona-sandbox``) registers its own token
        (e.g. ``"daytona"``). Boot reads ``pipe_func_config.execution_mode`` and calls the looked-up
        factory to produce the one PipeFunc executor set on the hub. ``factory`` is invoked at that boot
        apply-point, never here — so a factory may do heavy work (SDK import, config self-load) while
        ``register`` stays import-light. This is the PipeFunc-execution axis, orthogonal to the
        orchestration axis. Fail-loud on a duplicate mode, naming both plugins.
        """
        self._add(
            store=self.pipe_func_executors,
            sources=self._pipe_func_executor_sources,
            key=mode,
            value=factory,
            contribution=f"pipe_func executor {mode}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicatePipeFuncExecutorError(
                mode=mode, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_http_error_mapper(self, *, exc_type_provider: HttpErrorTypeProviderFn, to_error_report: HttpErrorMapperFn) -> None:
        """Contribute a mapping from a transport/runtime exception to a structured ``ErrorReport``.

        ``exc_type_provider`` is a thunk returning the concrete exception class the
        mapper applies to. It is resolved *lazily* by ``get_http_error_mappers`` (at a
        host runtime's app-construction time), never here — which is what keeps a
        plugin's ``register`` import-light: a plugin whose exception type lives in a
        heavy orchestrator SDK (``temporalio``) passes ``lambda: TemporalError`` and the
        SDK import is deferred until a host runtime actually consumes the mappers. The
        ``to_error_report`` closure is likewise uninvoked until an error is rendered.

        A host runtime (``pipelex-api``) iterates the resolved mappers at app
        construction and wraps each into one framework error handler (FastAPI, …) using
        its own RFC 7807 + disclosure rendering — so core and the plugin name no web
        framework. Duplicate-by-type detection is deferred to ``get_http_error_mappers``
        (the providers must run first); it stays fail-loud and names both plugins.
        """
        self.http_error_mappers.append(
            _HttpErrorMapperContribution(exc_type_provider=exc_type_provider, to_error_report=to_error_report, source_plugin=self._active.name)
        )
        self._active.contributions.append("http error mapper")

    def claim_content_generator(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.CONTENT_GENERATOR, factory=factory)

    def claim_pipe_func_executor(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_FUNC_EXECUTOR, factory=factory)

    def claim_pipe_router(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_ROUTER, factory=factory)

    def claim_pipe_run(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_RUN, factory=factory)

    def claim_task_manager(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.TASK_MANAGER, factory=factory)

    def claim_isolated_execution_probe(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.ISOLATED_EXECUTION_PROBE, factory=factory)

    def add_teardown(self, callback: Callable[[], None]) -> None:
        self.teardown_callbacks.append(callback)
        self._active.contributions.append("teardown callback")

    # ------------------------------------------------------------------ #
    # Read accessors (for host runtimes consuming plugin contributions)
    # ------------------------------------------------------------------ #

    @property
    def registered_plugin_names(self) -> set[str]:
        """Names of plugins that discovered and registered successfully.

        The authoritative namespace the ``plugins.boot_orchestrator`` gate matches against: a
        boot-orchestrator plugin claims its hub slots iff ``boot_orchestrator == its own name``.
        Disabled/broken discoveries are excluded — they never run ``register`` and so never claim a
        slot, making them invalid boot-orchestrator targets.
        """
        return {discovery.name for discovery in self.discoveries if discovery.status.is_registered}

    def get_http_error_mappers(self) -> dict[type[Exception], HttpErrorMapperFn]:
        """Resolve every contributed exc-type provider into a ``{exc_type: mapper}`` dict.

        The read view a host runtime (``pipelex-api``) iterates at app construction to
        register one framework error handler per exception type. Resolving the
        providers *here* (never at registration) is what lets a contributing plugin's
        ``register`` stay import-light: any orchestrator-SDK import a provider performs
        to name its concrete exception class is deferred to this call — which a host
        runtime makes only when it actually has the plugin (and therefore the SDK)
        installed, so the import always resolves. A freshly built dict, so a consumer
        cannot mutate the registrar's state. Fail-loud naming both plugins when two map
        the same resolved exception type.
        """
        resolved: dict[type[Exception], HttpErrorMapperFn] = {}
        sources: dict[type[Exception], str] = {}
        for contribution in self.http_error_mappers:
            exc_type = contribution.exc_type_provider()
            if exc_type in resolved:
                raise DuplicateHttpErrorMapperError(
                    exc_type=exc_type.__qualname__, first_plugin=sources[exc_type], second_plugin=contribution.source_plugin
                )
            resolved[exc_type] = contribution.to_error_report
            sources[exc_type] = contribution.source_plugin
        return resolved

    # ------------------------------------------------------------------ #

    def _add(
        self,
        *,
        store: dict[_RegistryKeyT, _RegistryValueT],
        sources: dict[_RegistryKeyT, str],
        key: _RegistryKeyT,
        value: _RegistryValueT,
        contribution: str,
        on_duplicate: Callable[[str, str], Exception],
    ) -> None:
        """Shared body for the keyed registration menu methods (mirrors ``_claim`` for the slot menu).

        Fail-loud duplicate detection, store, source attribution, and contribution
        recording in one place; each ``add_*`` method supplies its keyed store, the
        parallel sources dict, and a factory that builds its distinctly-typed
        ``Duplicate*Error`` naming both contributing plugins.
        """
        if key in store:
            raise on_duplicate(sources[key], self._active.name)
        store[key] = value
        sources[key] = self._active.name
        self._active.contributions.append(contribution)

    def _claim(self, *, slot: HubSlot, factory: Callable[[], Any]) -> None:
        if slot in self.slot_claims:
            raise HubSlotAlreadyClaimedError(slot=slot, first_plugin=self._slot_sources[slot], second_plugin=self._active.name)
        self.slot_claims[slot] = factory
        self._slot_sources[slot] = self._active.name
        self._active.contributions.append(f"hub slot {slot}")
