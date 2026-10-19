"""Single source of truth for the local / Temporal problem parity contract.

This module is **shipped in the open-core wheel on purpose**. The parity contract spans two
repos: open core asserts that a failing pipe surfaces a fully classified problem on the
local execution path, and our Temporal plugin asserts the *same*
problem survives the activity -> workflow -> submitter boundary. Both arms import the
fixtures below, so the classification a failing pipe surfaces cannot silently diverge between the
two execution paths — there is one definition, not two hand-synced copies.

Shipping it from core also gives third-party orchestrator-plugin authors a ready-made fixture to
prove their own backend preserves the problem across its boundary.

The only genuinely per-repo bit — the ``.mthds`` bundle each repo ships to drive the failing pipe
— is deliberately NOT here. Each arm subclasses these classes and adds its own ``BUNDLE_FILE``.
"""

from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind

from pipelex.cogt.exceptions import InferenceErrorCategory, JudgmentJobFailureError, LLMCompletionError, SearchJobFailureError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class ProblemParityTestData:
    """Constants + factory driving both arms of the local / Temporal problem parity test.

    A single deliberately-failing ``PipeLLM`` call is the source of truth for both arms: each runs
    the ``native_text_sequence`` pipe with the LLM call mocked to raise ``make_failing_llm_error()``,
    then asserts the resulting problem against the same ``EXPECTED_*`` classification.
    """

    PIPE_CODE: ClassVar[str] = "native_text_sequence"

    # The worker-side failure injected into the LLM call. CONFIGURATION is
    # non-retryable, so the Temporal activity is not retried and the workflow
    # fails on the first attempt — the test stays fast and deterministic.
    FAILURE_MESSAGE: ClassVar[str] = "LLM provider rejected the request: invalid API key"
    FAILURE_MODEL: ClassVar[str] = "gpt-4o-mini"
    FAILURE_PROVIDER: ClassVar[str] = "openai"
    FAILURE_CATEGORY: ClassVar[InferenceErrorCategory] = InferenceErrorCategory.CONFIGURATION
    FAILURE_USER_ACTION_DETAIL: ClassVar[str] = "Verify the API key configured for this provider."

    # The classification both arms must surface on the recovered problem: the code the category names, its domain, its
    # verdict and its step, and the model and the provider on the operator's diagnostics.
    EXPECTED_CODE: ClassVar[CoreCode] = CoreCode.RUNTIME_MISCONFIGURED
    EXPECTED_DOMAIN: ClassVar[ProblemDomain] = ProblemDomain.OPERATOR
    EXPECTED_RETRYABLE: ClassVar[bool] = False
    EXPECTED_OPERATOR_STEP_KIND: ClassVar[StepKind] = StepKind.FIX_CONFIGURATION
    # The advice the failure carries, which a local CLI prints as its tip and no problem carries.
    FAILURE_USER_ACTION_KIND: ClassVar[UserActionKind] = UserActionKind.CHECK_CREDENTIALS

    @classmethod
    def make_failing_llm_error(cls) -> LLMCompletionError:
        """Build a fresh classified ``LLMCompletionError``.

        Each arm builds its own instance — an exception carries traceback state,
        so a single shared instance must not be reused across runs.
        """
        error = LLMCompletionError(
            cls.FAILURE_MESSAGE,
            error_category=cls.FAILURE_CATEGORY,
            user_action=UserAction(kind=cls.FAILURE_USER_ACTION_KIND, detail=cls.FAILURE_USER_ACTION_DETAIL),
        )
        # model_handle / backend_name are declared on CogtError; a real worker fills them
        # at its public-method chokepoint. This test mocks above the worker, so set them
        # directly (mirrors tests/integration/pipelex/cli/agent_cli/test_run_error_chain.py).
        error.model_handle = cls.FAILURE_MODEL
        error.backend_name = cls.FAILURE_PROVIDER
        return error


class SearchProblemParityTestData:
    """Constants + factory driving both arms of the local / Temporal problem parity test for web search.

    The search counterpart of :class:`ProblemParityTestData`. A single deliberately-failing
    ``PipeSearch`` leaf is the source of truth for both arms: the local arm runs the ``native_search``
    pipe through the direct ``ContentGenerator`` with ``make_search_sourced_answer`` mocked to fail; the
    Temporal arm runs the same pipe through ``WfPipeRouter`` with the activity-side ``search_gen_sourced_answer``
    mocked to fail. Both assert the same ``EXPECTED_*`` classification.
    """

    PIPE_CODE: ClassVar[str] = "native_search"

    # The worker-side failure injected into the search call. CONFIGURATION is non-retryable, so the
    # Temporal activity is not retried and the workflow fails on the first attempt — fast and deterministic.
    FAILURE_MESSAGE: ClassVar[str] = "Search provider rejected the request: connection error"
    FAILURE_MODEL: ClassVar[str] = "linkup/standard"
    FAILURE_PROVIDER: ClassVar[str] = "linkup"
    FAILURE_CATEGORY: ClassVar[InferenceErrorCategory] = InferenceErrorCategory.CONFIGURATION
    FAILURE_USER_ACTION_DETAIL: ClassVar[str] = "Verify the API key configured for this search provider."

    # The classification both arms must surface on the recovered problem: the code the category names, its domain, its
    # verdict and its step, and the model and the provider on the operator's diagnostics.
    EXPECTED_CODE: ClassVar[CoreCode] = CoreCode.RUNTIME_MISCONFIGURED
    EXPECTED_DOMAIN: ClassVar[ProblemDomain] = ProblemDomain.OPERATOR
    EXPECTED_RETRYABLE: ClassVar[bool] = False
    EXPECTED_OPERATOR_STEP_KIND: ClassVar[StepKind] = StepKind.FIX_CONFIGURATION
    # The advice the failure carries, which a local CLI prints as its tip and no problem carries.
    FAILURE_USER_ACTION_KIND: ClassVar[UserActionKind] = UserActionKind.CHECK_CREDENTIALS

    @classmethod
    def make_failing_search_error(cls) -> SearchJobFailureError:
        """Build a fresh classified ``SearchJobFailureError``.

        Each arm builds its own instance — an exception carries traceback state, so a single shared
        instance must not be reused across runs.
        """
        error = SearchJobFailureError(
            cls.FAILURE_MESSAGE,
            error_category=cls.FAILURE_CATEGORY,
            user_action=UserAction(kind=cls.FAILURE_USER_ACTION_KIND, detail=cls.FAILURE_USER_ACTION_DETAIL),
        )
        # model_handle / backend_name are declared on CogtError; a real search worker fills them at its
        # public-method chokepoint. This test mocks above the worker, so set them directly.
        error.model_handle = cls.FAILURE_MODEL
        error.backend_name = cls.FAILURE_PROVIDER
        return error


class JudgeProblemParityTestData:
    """Constants + factory driving both arms of the local / Temporal problem parity test for judgment.

    The judgment counterpart of :class:`SearchProblemParityTestData`. A single deliberately-failing
    ``PipeJudge`` leaf is the source of truth for both arms: the local arm runs the ``native_judge`` pipe
    through the direct ``ContentGenerator`` with ``make_judgment_answers`` mocked to fail; a distributed
    arm runs the same pipe with its activity-side leaf mocked to fail. Both assert the same ``EXPECTED_*``
    classification.
    """

    PIPE_CODE: ClassVar[str] = "native_judge"

    # The worker-side failure injected into the judgment call. CONFIGURATION is non-retryable, so a
    # distributed activity is not retried and the workflow fails on the first attempt — fast and deterministic.
    FAILURE_MESSAGE: ClassVar[str] = "Judgment provider rejected the request: invalid API key"
    FAILURE_MODEL: ClassVar[str] = "jev-1.13.0"
    FAILURE_PROVIDER: ClassVar[str] = "typesafe"
    FAILURE_CATEGORY: ClassVar[InferenceErrorCategory] = InferenceErrorCategory.CONFIGURATION
    FAILURE_USER_ACTION_DETAIL: ClassVar[str] = "Verify the API key configured for this judgment provider."

    # The classification both arms must surface on the recovered problem: the code the category names, its domain, its
    # verdict and its step, and the model and the provider on the operator's diagnostics.
    EXPECTED_CODE: ClassVar[CoreCode] = CoreCode.RUNTIME_MISCONFIGURED
    EXPECTED_DOMAIN: ClassVar[ProblemDomain] = ProblemDomain.OPERATOR
    EXPECTED_RETRYABLE: ClassVar[bool] = False
    EXPECTED_OPERATOR_STEP_KIND: ClassVar[StepKind] = StepKind.FIX_CONFIGURATION
    # The advice the failure carries, which a local CLI prints as its tip and no problem carries.
    FAILURE_USER_ACTION_KIND: ClassVar[UserActionKind] = UserActionKind.CHECK_CREDENTIALS

    @classmethod
    def make_failing_judgment_error(cls) -> JudgmentJobFailureError:
        """Build a fresh classified ``JudgmentJobFailureError``.

        Each arm builds its own instance — an exception carries traceback state, so a single shared
        instance must not be reused across runs.
        """
        error = JudgmentJobFailureError(
            cls.FAILURE_MESSAGE,
            error_category=cls.FAILURE_CATEGORY,
            user_action=UserAction(kind=cls.FAILURE_USER_ACTION_KIND, detail=cls.FAILURE_USER_ACTION_DETAIL),
        )
        # model_handle / backend_name are declared on CogtError; a real judgment worker fills them at its
        # public-method chokepoint. This test mocks above the worker, so set them directly.
        error.model_handle = cls.FAILURE_MODEL
        error.backend_name = cls.FAILURE_PROVIDER
        return error
