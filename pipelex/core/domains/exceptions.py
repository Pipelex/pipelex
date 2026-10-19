from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class DomainCodeError(PipelexError):
    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class DomainFactoryError(PipelexError):
    """A domain the factory refuses after its blueprint passed the same validation, so an invariant."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
