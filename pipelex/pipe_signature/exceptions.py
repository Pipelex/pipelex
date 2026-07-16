from pipelex.base_exceptions import PipelexError


class PipeSignatureNotExecutableError(PipelexError):
    """Raised when a `PipeSignature` is invoked in live execution.

    Signatures are contract-only placeholders: they declare inputs and outputs but have
    no implementation. Encountering one at live-run time means the pipeline was not
    fully implemented before being launched.

    This is the **execute/run**-path guard. Validation no longer rejects signatures: a
    `PipeSignature` reached during a dry-run sweep is a runnability fact (`pending_signatures`
    + `is_runnable`), not a validation error (D-B). Running a stub, by contrast, must fail.
    """

    def __init__(self, pipe_ref: str) -> None:
        self.pipe_ref = pipe_ref
        message = (
            f"PipeSignature '{pipe_ref}' has no implementation and cannot be executed live. "
            f"Replace it with a real pipe before running, or validate with --allow-signatures."
        )
        super().__init__(message)
