"""Test data for PipeSearch E2E tests."""

from typing import ClassVar


class PipeSearchTestCases:
    """Test cases for PipeSearch E2E tests."""

    # (variant, pipe_code, input_name, input_value)
    SOURCED_QUERIES: ClassVar[list[tuple[str, str, str, str]]] = [
        ("news", "search_news_e2e", "topic", "Middle East"),
        # ("standard_preset", "search_sourced_e2e_using_preset", "topic", "the capital of France"),
        # ("deep_preset", "search_sourced_e2e_deep", "topic", "the main causes of climate change"),
    ]
