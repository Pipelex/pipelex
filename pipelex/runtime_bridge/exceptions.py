from pipelex.base_exceptions import PipelexError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


class PipelexRuntimeBridgeError(PipelexError):
    """Base for errors raised by the Pipelex runtime-bridge surface."""


class MissingOrchestratorError(PipelexRuntimeBridgeError):
    """Raised when no orchestrator is available for a requested execution mode.

    Covers both situations uniformly: the bridge resolves no orchestrator for the
    mode (e.g. ``MISTRAL_NATIVE`` when ``pipelex-mistralai-workflows`` is not
    installed — its plugin contributes no orchestrator), and an in-tree
    orchestrator that is registered but whose extra is absent (a ``TEMPORAL_*``
    mode without the ``pipelex[temporal]`` extra). The message is derived from the
    mode so each carries its exact, actionable install hint.
    """

    # The message carries the actionable pip-install hint; keep it under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, mode: PipelexExecutionMode):
        self.mode = mode
        super().__init__(self._build_message(mode=mode))

    @staticmethod
    def _build_message(*, mode: PipelexExecutionMode) -> str:
        match mode:
            case PipelexExecutionMode.TEMPORAL_BLOCKING | PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
                return "TEMPORAL_* execution modes require the pipelex[temporal] extra. Install with: pip install 'pipelex[temporal]'"
            case PipelexExecutionMode.MISTRAL_NATIVE:
                return (
                    "PipelexExecutionMode.MISTRAL_NATIVE requires the pipelex-mistralai-workflows "
                    "package. Install with: pip install pipelex-mistralai-workflows"
                )
            case PipelexExecutionMode.DIRECT:
                return (
                    "No orchestrator is registered for DIRECT mode. DIRECT is a core orchestrator that is always "
                    "available; this indicates a boot or plugin-discovery problem."
                )


class PipelexBridgeDispatchError(PipelexRuntimeBridgeError):
    """Raised when a pipe dispatched through the bridge fails (validation or execution)."""
