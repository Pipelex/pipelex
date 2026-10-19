from pipelex.cogt.exceptions import CogtError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class BedrockFactoryError(CogtError):
    """A Bedrock client the backend's settings cannot build, such as for an SDK handle it does not support."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class BedrockWorkerConfigurationError(CogtError):
    """A model spec missing a setting Bedrock requires, such as its ``max_tokens``."""

    error_code = PipelexErrorCode.CONFIG_INVALID
