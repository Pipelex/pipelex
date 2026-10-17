from pathlib import Path
from typing import Any

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError


class FixWriteConflictError(PipelexError):
    """A file changed after a fix or a migration read it but before the atomic commit."""

    error_code = CoreCode.METHOD_CHANGED_CONCURRENTLY


class FixTransactionError(PipelexUnexpectedError):
    """A multi-file commit failed and could not be fully rolled back."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class FixWriteFailedError(PipelexError):
    """A fix could not write a file it fixed: the file or its directory refused the write, and the round was rolled back.

    It is ``client.write_failed``, naming the file, or the directory a copy staged beside it could not be written in, and
    the system's reason, so a write failure is never read as a method file that cannot be read.
    """

    error_code = CoreCode.CLIENT_WRITE_FAILED

    def __init__(self, message: str, *, path: Path, reason: str):
        super().__init__(message)
        self.path = path
        self.reason = reason

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"path": str(self.path), "reason": self.reason}
