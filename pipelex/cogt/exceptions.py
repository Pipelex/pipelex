from pipelex.system.exceptions import FatalError, RootException
from pipelex.types import StrEnum


class CogtError(RootException):
    pass


class LLMConfigError(CogtError):
    pass


class ImageContentError(CogtError):
    pass


class InferenceManagerWorkerSetupError(CogtError, FatalError):
    pass


class CostRegistryError(CogtError):
    pass


class ReportingManagerError(CogtError):
    pass


class SdkTypeError(CogtError):
    pass


class SdkRegistryError(CogtError):
    pass


class LLMWorkerError(CogtError):
    pass


class LLMChoiceNotFoundError(CogtError):
    pass


class ExtractChoiceNotFoundError(CogtError):
    pass


class ImgGenChoiceNotFoundError(CogtError):
    pass


class LLMSettingsValidationError(CogtError):
    pass


class ImgGenSettingsValidationError(CogtError):
    pass


class ModelDeckValidatonError(CogtError):
    pass


class ModelNotFoundError(CogtError):
    pass


class LLMHandleNotFoundError(CogtError):
    pass


class LLMModelPlatformError(ValueError, CogtError):
    pass


class LLMModelDefinitionError(CogtError):
    pass


class LLMModelNotFoundError(CogtError):
    pass


class LLMCapabilityError(CogtError):
    pass


class LLMCompletionError(CogtError):
    pass


class LLMAssignmentError(CogtError):
    pass


class LLMPromptSpecError(CogtError):
    pass


class LLMPromptFactoryError(CogtError):
    pass


class LLMPromptTemplateInputsError(CogtError):
    pass


class LLMPromptParameterError(CogtError):
    pass


class PromptImageFactoryError(CogtError):
    pass


class PromptImageDefinitionError(CogtError):
    pass


class PromptImageFormatError(CogtError):
    pass


class ImgGenPromptError(CogtError):
    pass


class ImgGenParameterError(CogtError):
    pass


class ImgGenGenerationError(CogtError):
    pass


class ImgGenGeneratedTypeError(ImgGenGenerationError):
    pass


class MissingDependencyError(CogtError):
    """Raised when a required dependency is not installed."""

    def __init__(self, dependency_name: str, extra_name: str, message: str | None = None):
        self.dependency_name = dependency_name
        self.extra_name = extra_name
        error_msg = f"Required dependency '{dependency_name}' is not installed."
        if message:
            error_msg += f" {message}"
        error_msg += f" Please install it with 'pip install pipelex[{extra_name}]'."
        super().__init__(error_msg)


class MissingPluginError(CogtError):
    pass


class ExtractCapabilityError(CogtError):
    pass


class RoutingProfileLibraryNotFoundError(CogtError):
    pass


class RoutingProfileValidationError(CogtError):
    pass


class RoutingProfileLibraryError(CogtError):
    pass


class InferenceModelSpecError(CogtError):
    pass


class InferenceBackendError(CogtError):
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


class RoutingProfileError(CogtError):
    pass


class ModelManagerError(CogtError):
    pass


class ModelDeckNotFoundError(CogtError):
    pass


class ModelDeckValidationError(CogtError):
    pass
