from pipelex.cogt.exceptions import CogtError


class MistralPluginError(CogtError):
    pass


class MistralModelListingError(MistralPluginError):
    pass


class MistralWorkerConfigurationError(MistralPluginError):
    pass


class MistralExtractResponseError(MistralPluginError):
    pass
