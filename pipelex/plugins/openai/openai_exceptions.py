from pipelex.cogt.exceptions import CogtError
from pipelex.system.exceptions import CredentialsError


class OpenAIClientFactoryError(CogtError):
    _declared_title = "OpenAI client factory"


class VertexAIConfigError(CogtError):
    _declared_title = "VertexAI config"


class VertexAICredentialsError(CredentialsError):
    _declared_title = "VertexAI credentials"
