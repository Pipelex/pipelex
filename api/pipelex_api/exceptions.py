"""The runner's own error classes, each carrying its registry code.

Every class here is a :class:`~pipelex.base_exceptions.PipelexError` that declares its ``error_code`` in its own
body, as pipelex's error model requires (``pipelex/errors/error_code_declaration.py``), and the runner's gate test,
``tests/unit/test_error_code_gate.py``, fails the build on one that does not. They live in this module, rather than
beside the code that raises them, as every error class does: the same gate refuses one defined outside an
``exceptions.py`` or ``<topic>_exceptions.py`` module.

The API-authored refusals (``pipelex_api.errors.ApiError``, built from ``pipelex_api.error_types.ErrorType``) are a
separate family with no pipelex error behind them.
"""

from pipelex.base_exceptions import PipelexError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class ApiBootConfigError(PipelexError):
    """Raised at startup when the deployment's orchestration config cannot boot coherently."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class InvalidAuthModeError(PipelexError):
    """Raised at startup when `AUTH_MODE` holds a value that is not an `AuthMode` member."""

    error_code = PipelexErrorCode.CONFIG_INVALID
