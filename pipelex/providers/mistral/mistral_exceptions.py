from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class MistralPluginError(CogtError):
    """Base for the Mistral plugin's own errors, never raised directly."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class MistralModelListingError(MistralPluginError):
    """Mistral's model listing answered with no models, which only the model listing command reads."""

    error_code = CoreCode.PROVIDER_RESPONSE_INVALID


class MistralWorkerConfigurationError(MistralPluginError):
    """A model spec missing a setting Mistral requires, such as its ``max_tokens``."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class MistralExtractResponseError(MistralPluginError):
    """A Mistral OCR answer that cannot be used, such as an image without its base64 data."""

    error_code = CoreCode.PROVIDER_RESPONSE_INVALID
