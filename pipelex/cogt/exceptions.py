from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.base_exceptions import PipelexError
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_type import ModelType
    from pipelex.cogt.models.model_reference import ModelReferenceKind


class CogtError(PipelexError):
    pass


class LLMConfigError(CogtError):
    pass


class ImageContentError(CogtError):
    pass


class CostRegistryError(CogtError):
    pass


class ReportingManagerError(CogtError):
    pass


class SdkTypeError(CogtError):
    pass


class ModelChoiceNotFoundError(CogtError):
    """Error raised when a model choice cannot be found in the model deck.

    Includes available options and migration hints in error message.
    """

    def __init__(
        self,
        message: str,
        model_type: ModelType,
        model_choice: str,
        reference_kind: ModelReferenceKind | None = None,
        available_options: list[str] | None = None,
    ):
        self.model_type = model_type
        self.model_choice = model_choice
        self.reference_kind = reference_kind
        self.available_options = available_options or []

        full_message = message
        if self.available_options:
            options_str = ", ".join(sorted(self.available_options)[:10])
            if len(self.available_options) > 10:
                options_str += f" ... and {len(self.available_options) - 10} more"
            full_message += f"\n\nAvailable {reference_kind or 'options'}: {options_str}"

        super().__init__(message=full_message)


class LLMSettingsValidationError(CogtError):
    pass


class ImgGenSettingsValidationError(CogtError):
    pass


class ModelDeckValidatonError(CogtError):
    pass


class ModelDeckPresetValidatonError(ModelDeckValidatonError):
    def __init__(
        self,
        message: str,
        model_type: ModelType,
        preset_id: str,
        model_handle: str,
        enabled_backends: set[str] | None = None,
    ):
        self.model_type = model_type
        self.preset_id = preset_id
        self.model_handle = model_handle
        self.enabled_backends = enabled_backends or set()
        super().__init__(message)


class ModelNotFoundError(CogtError):
    def __init__(self, message: str, model_handle: str):
        self.model_handle = model_handle
        super().__init__(message)


class ModelWaterfallError(ModelNotFoundError):
    def __init__(self, message: str, model_handle: str, fallback_list: list[str]):
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message=message, model_handle=model_handle)


class LLMHandleNotFoundError(CogtError):
    def __init__(self, message: str, preset_id: str, model_handle: str, enabled_backends: set[str] | None = None):
        self.preset_id = preset_id
        self.model_handle = model_handle
        self.enabled_backends = enabled_backends or set()
        super().__init__(message)


class ImgGenHandleNotFoundError(CogtError):
    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class ExtractHandleNotFoundError(CogtError):
    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class SearchHandleNotFoundError(CogtError):
    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class ExtractOutputError(CogtError):
    pass


class GeneratedImageError(CogtError):
    pass


class LLMModelNotFoundError(ModelNotFoundError):
    pass


class LLMCapabilityError(CogtError):
    pass


class LLMCompletionError(CogtError):
    pass


class LLMAssignmentError(CogtError):
    pass


class LLMPromptSpecError(CogtError):
    pass


class LLMPromptTemplateInputsError(CogtError):
    pass


class LLMPromptParameterError(CogtError):
    pass


class PromptImageFactoryError(CogtError):
    pass


class PromptImageFormatError(CogtError):
    pass


class PromptDocumentFactoryError(CogtError):
    pass


class ImgGenModelNotFoundError(ModelNotFoundError):
    pass


class ImgGenPromptError(CogtError):
    pass


class ImgGenParameterError(CogtError):
    pass


class ImgGenGenerationError(CogtError):
    pass


class ImgGenGeneratedTypeError(ImgGenGenerationError):
    pass


class ExtractCapabilityError(CogtError):
    pass


class ExtractJobFailureError(CogtError):
    pass


class RoutingProfileLibraryNotFoundError(CogtError):
    pass


class RoutingProfileBlueprintValueError(CogtError, ValueError):
    pass


class RoutingProfileLibraryError(CogtError):
    pass


class InferenceModelSpecError(CogtError):
    pass


class InferenceBackendLibraryNotFoundError(CogtError):
    pass


class InferenceBackendLibraryValidationError(CogtError):
    pass


class InferenceBackendCredentialsErrorType(StrEnum):
    VAR_NOT_FOUND = "var_not_found"
    UNKNOWN_VAR_PREFIX = "unknown_var_prefix"
    VAR_FALLBACK_PATTERN = "var_fallback_pattern"


class InferenceBackendCredentialsError(CogtError):
    def __init__(
        self,
        error_type: InferenceBackendCredentialsErrorType,
        backend_name: str,
        message: str,
        key_name: str,
    ):
        self.error_type = error_type
        self.backend_name = backend_name
        self.key_name = key_name
        super().__init__(message)


class InferenceBackendLibraryError(CogtError):
    pass


class RoutingProfileDisabledBackendError(CogtError):
    pass


class ModelManagerError(CogtError):
    pass


class ModelDeckNotFoundError(CogtError):
    pass


class ModelDeckValidationError(CogtError):
    pass
