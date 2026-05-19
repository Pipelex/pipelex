from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class AnthropicCredentialsError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION
    user_action = UserAction(
        kind=UserActionKind.CHECK_CREDENTIALS,
        detail="Check that your Anthropic API key is valid and correctly configured",
    )


class AnthropicModelListingError(CogtError):
    pass


class AnthropicSDKUnsupportedError(CogtError):
    pass


class AnthropicWorkerConfigurationError(CogtError):
    pass
