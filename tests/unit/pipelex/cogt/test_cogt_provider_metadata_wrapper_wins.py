"""Pin: a wrapper ``CogtError``'s ``provider_metadata`` wins, even when the cause carries richer fields.

The operator's ``diagnostics.provider`` is the nearest provider fact along the cause chain, merged with a
whole-object ``or`` in :meth:`PipelexError._chain_facts` (``pipelex/base_exceptions.py``) over each error's
:meth:`CogtError.problem_facts` (``pipelex/cogt/exceptions.py``). A :class:`ProviderDiagnostics` instance is
always truthy regardless of internal state, so a wrapper that attached attribution-only metadata
(``status_code=None``) discards the cause's actionable ``status_code=429``.

No in-tree wrapper triggers this today (grep confirms only leaf workers set
non-None ``provider_metadata``), but the trap is latent. This test pins the
current wrapper-wins semantics so a future contributor changing the merge
strategy makes a deliberate decision and updates this test.
"""

from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import ProblemView, ProviderDiagnostics


class _WrapperCogtError(CogtError):
    """Stand-in wrapper that attaches attribution-only ``provider_metadata`` of its own.

    Inherits the OR-merge code path from ``CogtError``. ``error_category`` is
    set so the wrapper-level retryable computation does not stomp on the
    cause-derived value.
    """

    @override
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            error_category=InferenceErrorCategory.UNKNOWN,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="WrapperAttributionOnlyError",
                status_code=None,
                retry_after_seconds=None,
            ),
        )


class TestCogtProviderMetadataWrapperWins:
    def test_wrapper_provider_metadata_wins_even_when_cause_has_richer_metadata(self) -> None:
        leaf = LLMCompletionError(
            message="rate limited on the worker",
            error_category=InferenceErrorCategory.CAPACITY,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                status_code=429,
                retry_after_seconds=12.0,
            ),
        )
        try:
            try:
                raise leaf
            except LLMCompletionError as cause:
                raise _WrapperCogtError(message="wrapped while doing the thing") from cause
        except _WrapperCogtError as wrapper:
            problem = wrapper.to_problem(view=ProblemView.OPERATOR)
        # Wrapper-wins: the merged provider facts are the wrapper's, not the cause's.
        # The cause's actionable status_code=429 is dropped.
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "_WrapperCogtError"
        provider = problem.diagnostics.provider
        # The wrapper names no backend and no status, so its facts are empty, and the cause's 429 is not among them.
        assert provider == ProviderDiagnostics()
        assert provider is not None
        assert provider.status is None
