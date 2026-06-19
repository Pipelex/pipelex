from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel, Field

from pipelex.plugins.exceptions import (
    DuplicateInferenceBackendError,
    DuplicateOrchestratorError,
    HubSlotAlreadyClaimedError,
)
from pipelex.plugins.inference_backend_registry import InferenceFamily, MakeWorkerFn
from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


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


class CliCommand(NamedTuple):
    name: str
    help: str
    command: Callable[..., Any]


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
    keyed registries and applies the slot-claim thunks / CLI commands / teardown
    callbacks at their ordered apply-points.

    All duplicate detection is fail-loud and names both contributing plugins.
    """

    def __init__(self, *, config: "PipelexConfig"):
        self.config = config
        self.inference_backends: dict[tuple[InferenceFamily, str], MakeWorkerFn] = {}
        self.orchestrators: dict[PipelexExecutionMode, OrchestratorProtocol] = {}
        self.slot_claims: dict[HubSlot, Callable[[], Any]] = {}
        self.cli_commands: list[CliCommand] = []
        self.teardown_callbacks: list[Callable[[], None]] = []
        self.discoveries: list[PluginDiscovery] = []
        self._inference_sources: dict[tuple[InferenceFamily, str], str] = {}
        self._orchestrator_sources: dict[PipelexExecutionMode, str] = {}
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
        key = (family, sdk)
        if key in self.inference_backends:
            raise DuplicateInferenceBackendError(family=family, sdk=sdk, first_plugin=self._inference_sources[key], second_plugin=self._active.name)
        self.inference_backends[key] = make_worker
        self._inference_sources[key] = self._active.name
        self._active.contributions.append(f"inference backend {family}:{sdk}")

    def add_orchestrator(self, *, mode: PipelexExecutionMode, orchestrator: OrchestratorProtocol) -> None:
        if mode in self.orchestrators:
            raise DuplicateOrchestratorError(mode=mode, first_plugin=self._orchestrator_sources[mode], second_plugin=self._active.name)
        self.orchestrators[mode] = orchestrator
        self._orchestrator_sources[mode] = self._active.name
        self._active.contributions.append(f"orchestrator {mode}")

    def claim_content_generator(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.CONTENT_GENERATOR, factory=factory)

    def claim_pipe_router(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_ROUTER, factory=factory)

    def claim_pipe_run(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_RUN, factory=factory)

    def claim_task_manager(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.TASK_MANAGER, factory=factory)

    def add_cli_command(self, *, name: str, help: str, command: Callable[..., Any]) -> None:  # noqa: A002 - "help" mirrors typer's parameter name
        self.cli_commands.append(CliCommand(name=name, help=help, command=command))
        self._active.contributions.append(f"cli command {name}")

    def add_teardown(self, callback: Callable[[], None]) -> None:
        self.teardown_callbacks.append(callback)
        self._active.contributions.append("teardown callback")

    # ------------------------------------------------------------------ #

    def _claim(self, *, slot: HubSlot, factory: Callable[[], Any]) -> None:
        if slot in self.slot_claims:
            raise HubSlotAlreadyClaimedError(slot=slot, first_plugin=self._slot_sources[slot], second_plugin=self._active.name)
        self.slot_claims[slot] = factory
        self._slot_sources[slot] = self._active.name
        self._active.contributions.append(f"hub slot {slot}")
