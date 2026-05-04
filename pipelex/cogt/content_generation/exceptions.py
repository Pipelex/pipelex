from pipelex.base_exceptions import PipelexError, SecurityError


class NeitherUrlNorDataError(PipelexError):
    pass


class UnsafeSchemaError(SecurityError):
    pass
