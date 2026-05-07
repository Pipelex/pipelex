from pipelex.base_exceptions import PipelexError


class PipelexRuntimeBridgeError(PipelexError):
    """Base for errors raised by the Pipelex runtime-bridge surface."""


class MissingPipelexTemporalExtraError(PipelexRuntimeBridgeError):
    """Raised when a TEMPORAL_* execution mode is requested without the pipelex[temporal] extra."""


class PipelexBridgeRuntimeError(PipelexRuntimeBridgeError):
    """Raised when a pipe execution dispatched through the bridge fails."""
