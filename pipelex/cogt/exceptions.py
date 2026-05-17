from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.base_exceptions import ErrorReport, PipelexError
from pipelex.system.pipelex_service.types import RemoteConfigSource
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

    @property
    def is_retryable(self) -> bool:
        match self:
            case InferenceErrorCategory.TRANSIENT:
                return True
            case InferenceErrorCategory.CONFIGURATION | InferenceErrorCategory.CONTENT | InferenceErrorCategory.CAPACITY:
                return False


class CogtError(PipelexError):
    error_category: InferenceErrorCategory | None = None
    user_action: str | None = None

    def __init__(
        self,
        message: str,
        error_category: InferenceErrorCategory | None = None,
        user_action: str | None = None,
    ):
        super().__init__(message)
        if error_category is not None:
            self.error_category = error_category
        if user_action is not None:
            self.user_action = user_action

    @override
    def to_error_report(self) -> ErrorReport:
        return ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            error_category=self.error_category,
            retryable=self.error_category.is_retryable if self.error_category is not None else None,
            user_action=self.user_action,
            model=getattr(self, "model_handle", None),
            provider=getattr(self, "backend_name", None),
        )


class LLMConfigError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


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

    def __init__(self, message: str, model_handle: str):
        self.model_handle = model_handle
        super().__init__(message)


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
    user_action = "Check that the required API key environment variable is set"

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
    pass


class RoutingProfileDisabledBackendError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelManagerError(CogtError):
    pass


class ModelDeckNotFoundError(CogtError):
    pass


class ModelDeckValidationError(CogtError):
    pass


class GatewayUnknownModelError(CogtError):
    """A model handle referenced by the deck cannot be located in the active gateway specs.

    Carries the provenance of the gateway config (``FRESH`` vs ``CACHED``) so the message can
    branch: a cached-source failure suggests stale gateway specs and points the user at
    ``pipelex init`` to refresh while online; a fresh-source failure is a genuine
    misconfiguration.
    """

    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, model_name: str, source: RemoteConfigSource) -> None:
        self.model_name = model_name
        self.source = source
        match source:
            case RemoteConfigSource.FRESH:
                msg = (
                    f"Model handle '{model_name}' is referenced by the active model deck but is not present "
                    "in the Pipelex Gateway specs we just fetched. Either the model name is wrong, the gateway "
                    "no longer offers it, or your deck overrides need updating.\n"
                    "  - Run `pipelex doctor` to inspect the active gateway models.\n"
                    "  - Disable pipelex_gateway in .pipelex/inference/backends.toml to fall back to BYOK."
                )
            case RemoteConfigSource.CACHED:
                msg = (
                    f"Model handle '{model_name}' is referenced by the active model deck but is not present "
                    "in the Pipelex Gateway specs loaded from the on-disk cache. The cache may be stale.\n"
                    "  - Run `pipelex init` while online to refresh the cached gateway config.\n"
                    "  - Or disable pipelex_gateway in .pipelex/inference/backends.toml to operate offline (BYOK)."
                )
        super().__init__(msg)
