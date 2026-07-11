from pipelex.base_exceptions import PipelexError


class CodegenError(PipelexError):
    """Base error for the codegen projection engine (stamps, lock, check, emission)."""

    _declared_title = "Codegen error"


class CodegenStampError(CodegenError):
    """Raised when a generated file cannot be stamped (e.g. an unstampable file type)."""

    _declared_title = "Codegen stamp error"


class CodegenLockError(CodegenError):
    """Raised when a `codegen.lock` cannot be read or parsed."""

    _declared_title = "Codegen lock error"
