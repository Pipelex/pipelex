from typing import ClassVar

from pipelex.cogt.exceptions import CogtError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class PortkeyError(CogtError):
    """Base for the Portkey plugin's own errors, never raised directly."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class PortkeyFactoryError(PortkeyError):
    """A Portkey client the backend's settings cannot build, such as for an SDK handle it does not support."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class PortkeyCredentialsError(PortkeyError):
    """A Portkey backend with no API key configured."""

    error_code = PipelexErrorCode.CONFIG_CREDENTIAL_MISSING
