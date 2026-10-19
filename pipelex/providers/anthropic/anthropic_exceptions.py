from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class AnthropicModelListingError(CogtError):
    """Anthropic's model listing answered with no models, which only the model listing command reads."""

    error_code = CoreCode.PROVIDER_RESPONSE_INVALID


class AnthropicSDKUnsupportedError(CogtError):
    """An Anthropic client variant that cannot list models, which the plugin turns into ``ModelListingUnsupportedError``."""

    error_code = CoreCode.RUNTIME_UNSUPPORTED


class AnthropicWorkerConfigurationError(CogtError):
    """A model spec missing a setting Anthropic requires, such as its ``max_tokens``."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class AnthropicFactoryError(CogtError):
    """An Anthropic client the backend's settings cannot build.

    ``pipelex.config.invalid`` for an SDK handle or an authentication setting the backend gets wrong, and
    ``runtime.unexpected`` for an API key handed to the AWS request signer, which our own wiring does.
    """

    error_code = ErrorCodeSet(default=PipelexErrorCode.CONFIG_INVALID, others=(CoreCode.RUNTIME_UNEXPECTED,))
