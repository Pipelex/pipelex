from pipelex.base_exceptions import PipelexError


class WithImagesFilterError(PipelexError):
    """Raised when | with_images is used on a type without nested images."""


class UnusedInputError(PipelexError):
    """Raised when an input is declared but never referenced in the template."""
