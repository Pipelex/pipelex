from pipelex.cogt.exceptions import CogtError


class GroqModelListingError(CogtError):
    pass


class GroqSDKUnsupportedError(CogtError):
    pass


class GroqWorkerConfigurationError(CogtError):
    pass


class GroqFactoryError(CogtError):
    pass
