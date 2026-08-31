from typing import ClassVar

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import InferenceErrorCategory


class ExceptionTestData:
    # (topic, category, expected_is_retryable)
    CATEGORY_RETRYABLE_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, bool]]] = [
        ("transient_is_retryable", InferenceErrorCategory.TRANSIENT, True),
        ("configuration_not_retryable", InferenceErrorCategory.CONFIGURATION, False),
        ("content_not_retryable", InferenceErrorCategory.CONTENT, False),
        ("capacity_not_retryable", InferenceErrorCategory.CAPACITY, False),
        ("ambiguous_not_retryable", InferenceErrorCategory.AMBIGUOUS, False),
    ]

    # (topic, category, expected_error_domain, expected_http_status)
    # Exhaustive over InferenceErrorCategory — the exhaustiveness itself is asserted by
    # ``test_category_domain_cases_cover_every_category``, so a new category cannot be added
    # without deciding which domain it maps to.
    CATEGORY_DOMAIN_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, ErrorDomain | None, int]]] = [
        ("transient_is_runtime", InferenceErrorCategory.TRANSIENT, ErrorDomain.RUNTIME, 500),
        ("configuration_is_config", InferenceErrorCategory.CONFIGURATION, ErrorDomain.CONFIG, 500),
        ("content_is_input", InferenceErrorCategory.CONTENT, ErrorDomain.INPUT, 422),
        ("capacity_is_runtime", InferenceErrorCategory.CAPACITY, ErrorDomain.RUNTIME, 500),
        ("ambiguous_is_runtime", InferenceErrorCategory.AMBIGUOUS, ErrorDomain.RUNTIME, 500),
        ("unknown_asserts_no_domain", InferenceErrorCategory.UNKNOWN, None, 500),
    ]
