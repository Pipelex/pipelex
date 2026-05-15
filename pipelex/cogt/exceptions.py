from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.base_exceptions import ErrorReport, PipelexError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_type import ModelType
    from pipelex.cogt.models.model_reference import ModelReferenceKind


class InferenceErrorCategory(StrEnum):
    """Classifies inference errors for retry decisions and error reporting."""

    TRANSIENT = "transient"
    CONFIGURATION = "configuration"
    CONTENT = "content"
    CAPACITY = "capacity"
    UNKNOWN = "unknown"

    @property
    def is_retryable(self) -> bool:
        match self:
            case InferenceErrorCategory.TRANSIENT:
                return True
            case (
                InferenceErrorCategory.CONFIGURATION
                | InferenceErrorCategory.CONTENT
                | InferenceErrorCategory.CAPACITY
                | InferenceErrorCategory.UNKNOWN
            ):
                return False


class CogtError(PipelexError):
    error_category: InferenceErrorCategory | None = None
    user_action: UserAction | None = None
    provider_metadata: ProviderErrorMetadata | None = None

    def __init__(
        self,
        message: str,
        error_category: InferenceErrorCategory | None = None,
        user_action: UserAction | None = None,
        provider_metadata: ProviderErrorMetadata | None = None,
    ):
        super().__init__(message)
        if error_category is not None:
            self.error_category = error_category
        if user_action is not None:
            self.user_action = user_action
        if provider_metadata is not None:
            self.provider_metadata = provider_metadata

    @override
    def to_error_report(self) -> ErrorReport:
        return ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            error_category=self.error_category,
            error_domain=self.error_domain,
            retryable=self.error_category.is_retryable if self.error_category is not None else None,
            user_action=self.user_action,
            model=getattr(self, "model_handle", None),
            provider=getattr(self, "backend_name", None),
            provider_metadata=self.provider_metadata,
        )


class LLMConfigError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ImageContentError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class CostRegistryError(CogtError):
    pass


class ReportingManagerError(CogtError):
    pass


class SdkTypeError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelChoiceNotFoundError(CogtError):
    """Error raised when a model choice cannot be found in the model deck.

    Includes available options and migration hints in error message.
    """

    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(
        self,
        message: str,
        model_type: ModelType,
        model_choice: str,
        reference_kind: ModelReferenceKind | None = None,
        available_options: list[str] | None = None,
        suggestions: list[str] | None = None,
        wrong_sigil_hints: list[str] | None = None,
        cross_collection_suggestions: list[str] | None = None,
    ):
        self.model_type = model_type
        self.model_choice = model_choice
        self.reference_kind = reference_kind
        self.available_options = available_options or []
        self.suggestions = suggestions or []
        self.wrong_sigil_hints = wrong_sigil_hints or []
        self.cross_collection_suggestions = cross_collection_suggestions or []

        full_message = message

        all_suggestions = self.suggestions + self.cross_collection_suggestions
        if all_suggestions:
            full_message += "\n\nDid you mean: " + ", ".join(all_suggestions)

        for hint in self.wrong_sigil_hints:
            full_message += f"\nNote: {hint}"

        if not all_suggestions and not self.wrong_sigil_hints and self.available_options:
            options_str = ", ".join(sorted(self.available_options)[:10])
            if len(self.available_options) > 10:
                options_str += f" ... and {len(self.available_options) - 10} more"
            full_message += f"\n\nAvailable {reference_kind or 'options'}: {options_str}"

        super().__init__(message=full_message)


class LLMSettingsValidationError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ImgGenSettingsValidationError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelDeckValidatonError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


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
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(
        self,
        message: str,
        model_handle: str,
        error_category: InferenceErrorCategory | None = None,
        user_action: UserAction | None = None,
        provider_metadata: ProviderErrorMetadata | None = None,
    ):
        self.model_handle = model_handle
        super().__init__(
            message=message,
            error_category=error_category,
            user_action=user_action,
            provider_metadata=provider_metadata,
        )


class ModelWaterfallError(ModelNotFoundError):
    def __init__(self, message: str, model_handle: str, fallback_list: list[str]):
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message=message, model_handle=model_handle)


class LLMHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str, enabled_backends: set[str] | None = None):
        self.preset_id = preset_id
        self.model_handle = model_handle
        self.enabled_backends = enabled_backends or set()
        super().__init__(message)


class ImgGenHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class ExtractHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class SearchHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

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
    error_category = InferenceErrorCategory.CONFIGURATION


class LLMCompletionError(CogtError):
    pass


class LLMAssignmentError(CogtError):
    pass


class LLMPromptSpecError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class LLMPromptTemplateInputsError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class LLMPromptParameterError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptImageFactoryError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptImageFormatError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptDocumentFactoryError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class ImgGenModelNotFoundError(ModelNotFoundError):
    pass


class ImgGenPromptError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class ImgGenParameterError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class ImgGenGenerationError(CogtError):
    pass


class ImgGenGeneratedTypeError(ImgGenGenerationError):
    pass


class ExtractCapabilityError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ExtractJobFailureError(CogtError):
    pass


class SearchJobFailureError(CogtError):
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
    error_category = InferenceErrorCategory.CONFIGURATION
    user_action = UserAction(
        kind=UserActionKind.CHECK_CREDENTIALS,
        detail="Check that the required API key environment variable is set",
    )

    def __init__(
        self,
        credentials_error_type: InferenceBackendCredentialsErrorType,
        backend_name: str,
        message: str,
        key_name: str,
    ):
        self.credentials_error_type = credentials_error_type
        self.backend_name = backend_name
        self.key_name = key_name
        super().__init__(message)


class InferenceBackendLibraryError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class RoutingProfileDisabledBackendError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelManagerError(CogtError):
    pass


class ModelDeckNotFoundError(CogtError):
    pass


class ModelDeckValidationError(CogtError):
    pass
