class PipelexInterpreterError(Exception):
    """Base exception class for PipelexInterpreter errors."""


class PipelexConfigurationError(PipelexInterpreterError):
    """Raised when there are configuration issues with the PipelexInterpreter."""
