"""A wrapper ``CogtError``'s provider facts are merged over its cause's member by member, the wrapper's winning.

The operator's ``diagnostics.provider`` is assembled along the cause chain by :meth:`PipelexError.chain_facts`
(``pipelex/base_exceptions.py``) from each error's :meth:`CogtError.problem_facts` (``pipelex/cogt/exceptions.py``).
A wrapper that attaches attribution-only metadata, naming the backend but no status, must not discard the status, the
request id and the delay its cause recorded from the provider's answer, which an operator acts on.
"""

from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import ProblemView, ProviderDiagnostics


class _WrapperCogtError(CogtError):
    """Stand-in wrapper that attaches attribution-only ``provider_metadata`` of its own, with no status and no delay."""

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


class TestCogtProviderFactsMerge:
    def test_a_wrapper_keeps_what_its_cause_recorded_of_the_provider_answer(self) -> None:
        leaf = LLMCompletionError(
            message="rate limited on the worker",
            error_category=InferenceErrorCategory.TRANSIENT,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                status_code=429,
                retry_after_seconds=12.0,
                request_id="req_leaf",
            ),
        )
        leaf.fill_model_and_provider("gpt-4o-mini", backend_name="openai")
        try:
            try:
                raise leaf
            except LLMCompletionError as cause:
                wrapper = _WrapperCogtError(message="wrapped while doing the thing")
                wrapper.fill_model_and_provider(None, backend_name="openai_proxy")
                raise wrapper from cause
        except _WrapperCogtError as caught_wrapper:
            problem = caught_wrapper.to_problem(view=ProblemView.OPERATOR)

        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "_WrapperCogtError"
        # The wrapper's backend wins, and the cause's answer fills every member the wrapper left unset.
        assert problem.diagnostics.provider == ProviderDiagnostics(name="openai_proxy", status=429, request_id="req_leaf")
        assert problem.diagnostics.model == "gpt-4o-mini"
        assert problem.retry_after == 12.0
