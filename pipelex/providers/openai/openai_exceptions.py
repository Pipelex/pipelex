from pipelex.cogt.exceptions import CogtError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import CredentialsError


class OpenAIClientFactoryError(CogtError):
    """An OpenAI client the backend's settings cannot build: an SDK handle it does not support, or no Azure endpoint."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class VertexAIConfigError(CogtError):
    """A Vertex AI backend whose settings are missing or wrong, refused when the backends load."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class VertexAICredentialsError(CredentialsError):
    """Vertex AI credentials this process cannot read: no credentials file, or a token that is not a string."""

    error_code = PipelexErrorCode.CONFIG_CREDENTIAL_MISSING
