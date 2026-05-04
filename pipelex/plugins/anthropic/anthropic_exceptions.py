from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory


class AnthropicCredentialsError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION
    user_action = "Check that your Anthropic API key is valid and correctly configured"


class AnthropicModelListingError(CogtError):
    pass


class AnthropicSDKUnsupportedError(CogtError):
    pass


class AnthropicWorkerConfigurationError(CogtError):
    pass
