from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class ImgGenSettingValueError(PipelexError, ValueError):
    """An image generation setting whose values contradict each other, refused by its validator.

    A ``ValueError`` as well, so that pydantic wraps it into the validation error of the model being built: the
    method's bundle, or the model deck, whose boundary then reads the fault as its own.
    """

    error_code = CoreCode.METHOD_MODEL_SETTING_INVALID
