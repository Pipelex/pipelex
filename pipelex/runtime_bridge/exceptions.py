from pipelex.base_exceptions import PipelexError
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE, OrchestrationMode


class PipelexRuntimeBridgeError(PipelexError):
    """Base for errors raised by the Pipelex runtime-bridge surface."""


class MissingOrchestratorError(PipelexRuntimeBridgeError):
    """Raised when no orchestrator is registered for a requested orchestration mode.

    ``orchestration_mode`` is an open token: ``"direct"`` is contributed by core, and every
    other token by the plugin that owns its orchestrator (``"temporal"`` →
    our Temporal plugin, ``"mistral-workflows"`` → our Mistral Workflows plugin). A
    lookup miss therefore means *that mode's plugin is not installed* — the message is
    generic and names no orchestrator, so core stays fully decoupled from its plugins. The
    one special case is ``"direct"``: its orchestrator is core and always present, so a miss
    is a boot/discovery fault, not a missing plugin.
    """

    # The message is caller-actionable ("is its plugin installed?"); keep it under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, mode: OrchestrationMode):
        self.mode = mode
        super().__init__(_build_missing_message(noun="orchestrator", mode=mode))


class MissingBundleValidatorError(PipelexRuntimeBridgeError):
    """Raised when no bundle validator is registered for a requested orchestration mode.

    The ``/validate`` counterpart of ``MissingOrchestratorError``: ``"direct"`` is contributed
    by core and every other token by its owning plugin, so a lookup miss means that mode's
    plugin is not installed. The message is generic and names no orchestrator; ``"direct"`` is
    the boot/discovery special case (its validator is core and always present).
    """

    # The message is caller-actionable ("is its plugin installed?"); keep it under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, mode: OrchestrationMode):
        self.mode = mode
        super().__init__(_build_missing_message(noun="bundle validator", mode=mode))


def _build_missing_message(*, noun: str, mode: OrchestrationMode) -> str:
    """Generic, plugin-decoupled message shared by both Missing* errors.

    A plain string compare on ``"direct"`` (not an enum ``match``) — core's one built-in
    token — singles out the boot/discovery fault from the missing-plugin case.
    """
    if mode == DIRECT_ORCHESTRATION_MODE:
        return f"No {noun} is registered for the core '{DIRECT_ORCHESTRATION_MODE}' mode; this indicates a boot or plugin-discovery problem."
    return f"No {noun} is registered for orchestration mode '{mode}'; is its plugin installed?"


class PipelexBridgeDispatchError(PipelexRuntimeBridgeError):
    """Raised when a pipe dispatched through the bridge fails (validation or execution)."""
