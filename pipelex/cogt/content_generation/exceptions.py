from pipelex.base_exceptions import ErrorDomain, PipelexError, SecurityError


class NeitherUrlNorDataError(PipelexError):
    pass


class UnsafeSchemaError(SecurityError):
    pass


class MockInferenceUnsupportedError(PipelexError):
    """Raised when ``--mock-inference`` reaches an inference operation that has no leaf-level mock.

    ``--mock-inference`` is honored only at the LLM leaf, which returns synthetic text/objects with
    reportable usage and never calls a provider. Image generation, document extraction, and web search
    have no such leaf mock yet, so under ``--mock-inference`` they would dispatch to the **real** provider
    and spend real money — the exact opposite of what the flag promises. This guard fails loud at those
    leaves instead of silently spending. Full no-spend coverage of every operator is available today via
    ``--dry-run``; per-operator leaf mocks land later (``wip/dry-run-refactor/followup-leaf-run-mode-mock.md``,
    via ``run_mode=DRY``).
    """

    # The caller picked an unsupported flag/operation combination they can fix (drop --mock-inference
    # for this pipe, or use --dry-run) — caller-fixable input, not a server-side fault.
    error_domain = ErrorDomain.INPUT
    # The message is pure caller-facing guidance (names the operation, points at --dry-run) with no
    # internal paths or secrets, so it should survive STRICT disclosure intact.
    _authors_caller_facing_message = True

    @classmethod
    def for_operation(cls, operation: str) -> "MockInferenceUnsupportedError":
        """Build the guard error for a named inference operation (e.g. ``"image generation (PipeImgGen)"``)."""
        return cls(
            f"--mock-inference does not support {operation}: it has no leaf-level mock, so the run would "
            "call the real provider and spend. Use --dry-run for full no-spend coverage."
        )
