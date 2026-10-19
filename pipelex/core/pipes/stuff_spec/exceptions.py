from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class StuffSpecFactoryError(PipelexError):
    """An output concept spec that does not parse, or names a concept that does not resolve."""

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION
