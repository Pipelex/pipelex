from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class ExceptionTestData:
    # (topic, category, expected_is_retryable)
    CATEGORY_RETRYABLE_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, bool]]] = [
        ("transient_is_retryable", InferenceErrorCategory.TRANSIENT, True),
        ("configuration_not_retryable", InferenceErrorCategory.CONFIGURATION, False),
        ("content_not_retryable", InferenceErrorCategory.CONTENT, False),
        ("capacity_not_retryable", InferenceErrorCategory.CAPACITY, False),
    ]
