from pipelex.base_exceptions import PipelexError


class PipeSignatureNotExecutableError(PipelexError):
    """Raised when a `PipeSignature` is invoked in live execution.

    Signatures are contract-only placeholders: they declare inputs and outputs but have
    no implementation. Encountering one at live-run time means the pipeline was not
    fully implemented before being launched.
    """

    def __init__(self, pipe_ref: str) -> None:
        self.pipe_ref = pipe_ref
        message = (
            f"PipeSignature '{pipe_ref}' has no implementation and cannot be executed live. "
            f"Replace it with a real pipe before running, or validate with --allow-signatures."
        )
        super().__init__(message)
