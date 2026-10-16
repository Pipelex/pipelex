from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class WithImagesFilterError(PipelexError):
    """Raised when | with_images is used on a type without nested images: a template of the method that cannot work."""

    error_code = CoreCode.METHOD_TEMPLATE_INVALID
