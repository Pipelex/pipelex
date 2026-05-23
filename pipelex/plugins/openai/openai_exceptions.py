from pipelex.cogt.exceptions import CogtError
from pipelex.system.exceptions import CredentialsError


class OpenAIClientFactoryError(CogtError):
    pass


class VertexAIConfigError(CogtError):
    pass


class VertexAICredentialsError(CredentialsError):
    pass
