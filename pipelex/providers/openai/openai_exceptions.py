from pipelex.cogt.exceptions import CogtError
from pipelex.system.exceptions import CredentialsError


class OpenAIClientFactoryError(CogtError):
    _declared_title = "OpenAI client factory error"


class VertexAIConfigError(CogtError):
    _declared_title = "VertexAI configuration error"


class VertexAICredentialsError(CredentialsError):
    _declared_title = "VertexAI credentials error"
