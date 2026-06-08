from pipelex.base_exceptions import PipelexError


class PipelexRuntimeBridgeError(PipelexError):
    """Base for errors raised by the Pipelex runtime-bridge surface."""


class MissingPipelexTemporalExtraError(PipelexRuntimeBridgeError):
    """Raised when a TEMPORAL_* execution mode is requested without the pipelex[temporal] extra."""

    # The message carries the actionable pip-install hint; keep it under STRICT disclosure.
    _authors_caller_facing_message = True


class MissingMistralWorkflowsPluginError(PipelexRuntimeBridgeError):
    """Raised when MISTRAL_NATIVE mode is requested without ``pipelex-mistralai-workflows`` installed."""

    # The message carries the actionable pip-install hint; keep it under STRICT disclosure.
    _authors_caller_facing_message = True


class PipelexBridgeDispatchError(PipelexRuntimeBridgeError):
    """Raised when a pipe dispatched through the bridge fails (validation or execution)."""
