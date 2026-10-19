from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class LinkupError(CogtError):
    """Base for every error this backend raises, so callers can catch the provider as a family.

    Raised itself for a backend with no API key, which is the deployment's missing credential.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = PipelexErrorCode.CONFIG_CREDENTIAL_MISSING


class LinkupSearchResponseError(LinkupError):
    """The Linkup API answered a structured search with a payload shape the leaf cannot validate."""

    error_code = CoreCode.PROVIDER_RESPONSE_INVALID


class LinkupSearchEmptyResultError(LinkupError):
    """The Linkup API answered a structured search with no object payload to fill the output structure."""

    error_code = CoreCode.MODEL_NO_RESULT
