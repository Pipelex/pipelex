"""Shared test data for the local / Temporal ``ErrorReport`` parity pair.

A single deliberately-failing ``PipeLLM`` call is the source of truth for both
arms of the parity check:

- the Temporal full-chain test (now in the external ``pipelex-temporal`` distribution:
  ``tests/integration/pipelex_temporal/test_workflow_error_report_full_chain.py``),
- the local full-chain test
  (``tests/integration/pipelex/error_handling/test_error_report_local_full_chain.py``).

Both run the same ``native_text_sequence`` pipe with the LLM call mocked to raise
``make_failing_llm_error()``, then assert the resulting ``ErrorReport`` against the
same ``EXPECTED_*`` classification constants. Because both arms are pinned to the
same constants, local / Temporal parity holds by construction: if either path
drops a classification field, that arm fails.
"""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, SearchJobFailureError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class ErrorReportParityTestData:
    """Constants driving both arms of the local / Temporal ``ErrorReport`` parity test."""

    # The failing pipe: a native-Text PipeSequence whose first step is a PipeLLM. The
    # bundle lives beside this test; it was shared with the Temporal parity arm, now in
    # the external ``pipelex-temporal`` distribution (cross-repo parity via shared constants).
    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/error_handling/bundles/native_text_sequence.mthds"
    PIPE_CODE: ClassVar[str] = "native_text_sequence"

    # The worker-side failure injected into the LLM call. CONFIGURATION is
    # non-retryable, so the Temporal activity is not retried and the workflow
    # fails on the first attempt — the test stays fast and deterministic.
    FAILURE_MESSAGE: ClassVar[str] = "LLM provider rejected the request: invalid API key"
    FAILURE_MODEL: ClassVar[str] = "gpt-4o-mini"
    FAILURE_PROVIDER: ClassVar[str] = "openai"
    FAILURE_CATEGORY: ClassVar[InferenceErrorCategory] = InferenceErrorCategory.CONFIGURATION
    FAILURE_USER_ACTION_DETAIL: ClassVar[str] = "Verify the API key configured for this provider."

    # The classification both arms must surface on the recovered ErrorReport.
    EXPECTED_RETRYABLE: ClassVar[bool] = False
    EXPECTED_USER_ACTION_KIND: ClassVar[UserActionKind] = UserActionKind.CHECK_CREDENTIALS

    @classmethod
    def make_failing_llm_error(cls) -> LLMCompletionError:
        """Build a fresh classified ``LLMCompletionError``.

        Each arm builds its own instance — an exception carries traceback state,
        so a single shared instance must not be reused across runs.
        """
        error = LLMCompletionError(
            cls.FAILURE_MESSAGE,
            error_category=cls.FAILURE_CATEGORY,
            user_action=UserAction(kind=cls.EXPECTED_USER_ACTION_KIND, detail=cls.FAILURE_USER_ACTION_DETAIL),
        )
        # model_handle / backend_name are declared on CogtError; a real worker fills them
        # at its public-method chokepoint. This test mocks above the worker, so set them
        # directly (mirrors tests/integration/pipelex/cli/agent_cli/test_run_error_chain.py).
        error.model_handle = cls.FAILURE_MODEL
        error.backend_name = cls.FAILURE_PROVIDER
        return error


class SearchErrorReportParityTestData:
    """Constants driving both arms of the local / Temporal ``ErrorReport`` parity test for web search.

    The search counterpart of :class:`ErrorReportParityTestData`. A single deliberately-failing
    ``PipeSearch`` leaf is the source of truth for both arms: the local arm runs the ``native_search``
    pipe through the direct ``ContentGenerator`` with ``make_search_sourced_answer`` mocked to fail; the
    Temporal arm runs the same pipe through ``WfPipeRouter`` with the activity-side ``search_gen_sourced_answer``
    mocked to fail. Both assert the same ``EXPECTED_*`` classification, so parity holds by construction.
    """

    # A single-step PipeSearch bundle over the native SearchResult concept — no inputs, no dynamic classes.
    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/error_handling/bundles/native_search.mthds"
    PIPE_CODE: ClassVar[str] = "native_search"

    # The worker-side failure injected into the search call. CONFIGURATION is non-retryable, so the
    # Temporal activity is not retried and the workflow fails on the first attempt — fast and deterministic.
    FAILURE_MESSAGE: ClassVar[str] = "Search provider rejected the request: connection error"
    FAILURE_MODEL: ClassVar[str] = "linkup/standard"
    FAILURE_PROVIDER: ClassVar[str] = "linkup"
    FAILURE_CATEGORY: ClassVar[InferenceErrorCategory] = InferenceErrorCategory.CONFIGURATION
    FAILURE_USER_ACTION_DETAIL: ClassVar[str] = "Verify the API key configured for this search provider."

    # The classification both arms must surface on the recovered ErrorReport.
    EXPECTED_RETRYABLE: ClassVar[bool] = False
    EXPECTED_USER_ACTION_KIND: ClassVar[UserActionKind] = UserActionKind.CHECK_CREDENTIALS

    @classmethod
    def make_failing_search_error(cls) -> SearchJobFailureError:
        """Build a fresh classified ``SearchJobFailureError``.

        Each arm builds its own instance — an exception carries traceback state, so a single shared
        instance must not be reused across runs.
        """
        error = SearchJobFailureError(
            cls.FAILURE_MESSAGE,
            error_category=cls.FAILURE_CATEGORY,
            user_action=UserAction(kind=cls.EXPECTED_USER_ACTION_KIND, detail=cls.FAILURE_USER_ACTION_DETAIL),
        )
        # model_handle / backend_name are declared on CogtError; a real search worker fills them at its
        # public-method chokepoint. This test mocks above the worker, so set them directly.
        error.model_handle = cls.FAILURE_MODEL
        error.backend_name = cls.FAILURE_PROVIDER
        return error
