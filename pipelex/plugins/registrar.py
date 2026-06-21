from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, Field

from pipelex.base_exceptions import ErrorReport
from pipelex.plugins.exceptions import (
    DuplicateHttpErrorMapperError,
    DuplicateInferenceBackendError,
    DuplicateModelListerError,
    DuplicateOrchestratorError,
    HubSlotAlreadyClaimedError,
)
from pipelex.plugins.inference_backend_registry import InferenceFamily, MakeWorkerFn
from pipelex.plugins.model_lister_registry import ListModelsFn
from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


_RegistryKeyT = TypeVar("_RegistryKeyT")
_RegistryValueT = TypeVar("_RegistryValueT")

# A plugin's framework-agnostic mapping from one transport/runtime exception to a
# structured ``ErrorReport``. A host runtime (``pipelex-api``) renders the report
# into its own HTTP error response (RFC 7807 + disclosure) — so core and the plugin
# name no web framework.
HttpErrorMapperFn = Callable[[Exception], ErrorReport]


class HubSlot(StrEnum):
    """A process-global capability slot a boot-orchestrator plugin may claim."""

    CONTENT_GENERATOR = "content_generator"
    PIPE_ROUTER = "pipe_router"
    PIPE_RUN = "pipe_run"
    TASK_MANAGER = "task_manager"


class PluginOrigin(StrEnum):
    BUILTIN = "builtin"
    EXTERNAL = "external"


class PluginStatus(StrEnum):
    REGISTERED = "registered"
    DISABLED = "disabled"
    BROKEN = "broken"


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
        self.orchestrators: dict[PipelexExecutionMode, OrchestratorProtocol] = {}
        self.http_error_mappers: dict[type[Exception], HttpErrorMapperFn] = {}
        self.slot_claims: dict[HubSlot, Callable[[], Any]] = {}
        self.teardown_callbacks: list[Callable[[], None]] = []
        self.discoveries: list[PluginDiscovery] = []
        self._inference_sources: dict[tuple[InferenceFamily, str], str] = {}
        self._model_lister_sources: dict[str, str] = {}
        self._orchestrator_sources: dict[PipelexExecutionMode, str] = {}
        self._http_error_mapper_sources: dict[type[Exception], str] = {}
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

    def add_orchestrator(self, *, mode: PipelexExecutionMode, orchestrator: OrchestratorProtocol) -> None:
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

    def add_http_error_mapper(self, *, exc_type: type[Exception], to_error_report: HttpErrorMapperFn) -> None:
        """Contribute a mapping from a transport/runtime exception to a structured ``ErrorReport``.

        A host runtime (``pipelex-api``) iterates the collected mappers at app
        construction and wraps each into one framework error handler (FastAPI, …)
        using its own RFC 7807 + disclosure rendering — so core and the plugin name
        no web framework. Keeps the plugin import-light: ``register`` only records
        the closure, which may import the orchestrator SDK lazily when first
        invoked, never at registration time.
        """
        self._add(
            store=self.http_error_mappers,
            sources=self._http_error_mapper_sources,
            key=exc_type,
            value=to_error_report,
            contribution=f"http error mapper {exc_type.__qualname__}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateHttpErrorMapperError(
                exc_type=exc_type.__qualname__, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def claim_content_generator(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.CONTENT_GENERATOR, factory=factory)

    def claim_pipe_router(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_ROUTER, factory=factory)

    def claim_pipe_run(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_RUN, factory=factory)

    def claim_task_manager(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.TASK_MANAGER, factory=factory)

    def add_teardown(self, callback: Callable[[], None]) -> None:
        self.teardown_callbacks.append(callback)
        self._active.contributions.append("teardown callback")

    # ------------------------------------------------------------------ #
    # Read accessors (for host runtimes consuming plugin contributions)
    # ------------------------------------------------------------------ #

    def get_http_error_mappers(self) -> dict[type[Exception], HttpErrorMapperFn]:
        """Return a copy of the HTTP-error mappers contributed by discovered plugins.

        The read view a host runtime (``pipelex-api``) iterates at app construction
        to register one framework error handler per exception type. A copy, so a
        consumer cannot mutate the registrar's accumulated state.
        """
        return dict(self.http_error_mappers)

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
