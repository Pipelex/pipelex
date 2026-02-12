from pipelex.base_exceptions import PipelexError


class ManifestError(PipelexError):
    pass


class ManifestParseError(ManifestError):
    pass


class ManifestValidationError(ManifestError):
    pass
