"""Test data for PipeExtract E2E tests."""

from typing import ClassVar

from tests.cases.documents import DocumentTestCases


class PipeExtractTestCases:
    """Test cases for PipeExtract E2E tests."""

    # (variant, url)
    # WEB_URL_3 (AllRecipes) is a known bot-blocked site that returns 403 to HEAD requests
    # but serves the actual content fine through linkup-fetch. Included here to guard
    # against regressions where the pre-flight URL check aborts the pipeline.
    WEB_URL_CASES: ClassVar[list[tuple[str, str]]] = [
        ("books_toscrape", DocumentTestCases.WEB_URL_1),
        ("scrapethissite", DocumentTestCases.WEB_URL_2),
        ("allrecipes_bot_blocked", DocumentTestCases.WEB_URL_3),
    ]
