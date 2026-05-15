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


class SignaturesNotAllowedError(PipelexError):
    """Raised in strict validation when one or more `PipeSignature` placeholders are reachable.

    Strict mode (the default) refuses to dry-run any pipe whose dependency graph contains a
    `PipeSignature` — they are contract-only stubs and a strict caller is asking for a
    fully-implemented pipeline. Lenient mode (`allow_signatures=True`) bypasses this check.
    """

    def __init__(
        self,
        offending_pipe_refs: set[str],
        signature_refs: set[str],
        dep_paths: dict[str, list[str]],
    ) -> None:
        self.offending_pipe_refs = offending_pipe_refs
        self.signature_refs = signature_refs
        self.dep_paths = dep_paths
        message = self._format_message()
        super().__init__(message)

    def _format_message(self) -> str:
        sorted_offenders = sorted(self.offending_pipe_refs)
        if len(sorted_offenders) == 1:
            header = f"Pipe '{sorted_offenders[0]}' depends on PipeSignature placeholders that have no implementation:"
        elif len(sorted_offenders) > 1:
            offender_list = ", ".join(f"'{ref}'" for ref in sorted_offenders)
            header = f"The following pipes depend on PipeSignature placeholders that have no implementation: {offender_list}"
        else:
            header = "Validation found PipeSignature placeholders that have no implementation:"
        lines: list[str] = [header]
        for sig_ref in sorted(self.signature_refs):
            dep_chain = self.dep_paths.get(sig_ref, [])
            if dep_chain:
                chain_str = " → ".join([*dep_chain, sig_ref])
                lines.append(f"  - {sig_ref} (via {chain_str})")
            else:
                lines.append(f"  - {sig_ref}")
        lines.append("Replace each signature with a real implementation, or re-run with `--allow-signatures` to accept placeholders.")
        return "\n".join(lines)
