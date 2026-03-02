"""Test data for PipeSearch E2E tests."""

from typing import ClassVar


class PipeSearchTestCases:
    """Test cases for PipeSearch E2E tests."""

    # (variant, pipe_code, query)
    SOURCED_QUERIES: ClassVar[list[tuple[str, str, str]]] = [
        ("standard_preset", "search_sourced_e2e_using_preset", "What is the capital of France?"),
        ("deep_preset", "search_sourced_e2e_deep", "What are the main causes of climate change?"),
    ]
