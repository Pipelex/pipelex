"""Custom exceptions for the Pipelex core module."""


class PipelexInterpreterError(Exception):
    """Base exception class for PipelexInterpreter errors."""


class PipelexConfigurationError(PipelexInterpreterError):
    """Raised when there are configuration issues with the PipelexInterpreter."""


class PipelexUnknownPipeError(PipelexInterpreterError):
    """Raised when encountering an unknown pipe blueprint type."""
