from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.errors.error_codes import ErrorCode


class ExceptionTestData:
    # (topic, category, expected_is_retryable)
    CATEGORY_RETRYABLE_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, bool]]] = [
        ("transient_is_retryable", InferenceErrorCategory.TRANSIENT, True),
        ("configuration_not_retryable", InferenceErrorCategory.CONFIGURATION, False),
        ("content_not_retryable", InferenceErrorCategory.CONTENT, False),
        ("capacity_not_retryable", InferenceErrorCategory.CAPACITY, False),
        ("ambiguous_not_retryable", InferenceErrorCategory.AMBIGUOUS, False),
    ]

    # (topic, category, expected_code, expected_domain, expected_retryable)
    # What a failure built by hand with a category and no code reports. Exhaustive over InferenceErrorCategory — the
    # exhaustiveness itself is asserted by ``test_category_code_cases_cover_every_category``, so a new category cannot
    # be added without deciding what such a failure reports.
    CATEGORY_CODE_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, ErrorCode, ProblemDomain, bool]]] = [
        ("transient_invites_a_retry", InferenceErrorCategory.TRANSIENT, CoreCode.PROVIDER_UNAVAILABLE, ProblemDomain.RUNTIME, True),
        ("configuration_is_the_operator_s", InferenceErrorCategory.CONFIGURATION, CoreCode.RUNTIME_MISCONFIGURED, ProblemDomain.OPERATOR, False),
        ("content_keeps_the_fallback", InferenceErrorCategory.CONTENT, CoreCode.RUNTIME_UNEXPECTED, ProblemDomain.RUNTIME, False),
        ("capacity_is_the_quota", InferenceErrorCategory.CAPACITY, CoreCode.PROVIDER_QUOTA_EXHAUSTED, ProblemDomain.OPERATOR, False),
        ("ambiguous_is_an_unknown_outcome", InferenceErrorCategory.AMBIGUOUS, CoreCode.PROVIDER_OUTCOME_UNKNOWN, ProblemDomain.RUNTIME, True),
        ("unknown_keeps_the_fallback", InferenceErrorCategory.UNKNOWN, CoreCode.RUNTIME_UNEXPECTED, ProblemDomain.RUNTIME, False),
    ]
