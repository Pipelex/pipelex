from pipelex.base_exceptions import PipelexError


class MistralWorkflowsPluginError(PipelexError):
    """Base for errors raised by the mistralai-workflows plugin."""


class MistralWorkflowsNotInstalledError(MistralWorkflowsPluginError, ImportError):
    """Raised when the optional `mistralai-workflows` dependency is missing."""


class MissingPipelexTemporalExtraError(MistralWorkflowsPluginError):
    """Raised when a TEMPORAL_* execution mode is requested without the pipelex[temporal] extra."""


class PipelexBridgeRuntimeError(MistralWorkflowsPluginError):
    """Raised when a pipe execution dispatched through the bridge fails."""
