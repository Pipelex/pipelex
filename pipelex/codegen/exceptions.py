from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class CodegenError(PipelexError):
    """Base error for the codegen projection engine (stamps, lock, check, emission).

    Raised directly when an output path conflicts with what is already there: a file codegen does not own, or
    an artifact path that escapes the root, is not a file, or passes through a symlink.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = PipelexErrorCode.CODEGEN_OUTPUT_CONFLICT


class CodegenStampError(CodegenError):
    """Raised when a generated file cannot be stamped (e.g. an unstampable file type), a fault of the emitter."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class CodegenLockError(CodegenError):
    """Raised when a `codegen.lock` cannot be read or parsed.

    A malformed lock is ``pipelex.codegen.lock_invalid``; a lock of an unknown or newer format version, which
    a newer build reads, is ``pipelex.codegen.lock_unsupported``.
    """

    error_code = ErrorCodeSet(default=PipelexErrorCode.CODEGEN_LOCK_INVALID, others=(PipelexErrorCode.CODEGEN_LOCK_UNSUPPORTED,))
