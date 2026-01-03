from pipelex.base_exceptions import PipelexError


class StuffError(PipelexError):
    pass


class StuffFactoryError(StuffError):
    pass


class StuffContentFactoryError(StuffError):
    pass


class StuffArtefactError(StuffError):
    pass


class StuffArtefactReservedFieldError(StuffArtefactError):
    pass


class StuffContentTypeError(StuffError):
    def __init__(self, message: str, expected_type: str, actual_type: str):
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(message)


class StuffContentValidationError(StuffError):
    """Raised when content validation fails during type conversion."""

    def __init__(self, original_type: str, target_type: str, validation_error: str):
        self.original_type = original_type
        self.target_type = target_type
        self.validation_error = validation_error
        super().__init__(f"Failed to validate content from {original_type} to {target_type}: {validation_error}")
