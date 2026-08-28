from typing import Any

import pytest

from pipelex.core.stuffs.html_content import HtmlContent
from tests.unit.pipelex.core.stuffs.html_content.test_data import TestData


class TestHtmlContentSmartDump:
    """Tests for HtmlContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump always returns a dict with inner_html and css_class."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_without_css_class(self):
        """An unset optional css_class dumps as None — the field stays in the payload, unset."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML)
        assert content.smart_dump() == TestData.EXPECTED_SMART_DUMP_NO_CLASS

    @pytest.mark.parametrize(
        ("inner_html", "css_class", "expected_output"),
        [
            ("", "", {"inner_html": "", "css_class": ""}),
            ("<div>test</div>", "container", {"inner_html": "<div>test</div>", "css_class": "container"}),
            ("plain text", "highlight", {"inner_html": "plain text", "css_class": "highlight"}),
            ("<p>bare</p>", None, {"inner_html": "<p>bare</p>", "css_class": None}),
        ],
    )
    def test_smart_dump_various_inputs(self, inner_html: str, css_class: str | None, expected_output: dict[str, Any]):
        """Verify smart_dump handles various inputs correctly."""
        content = HtmlContent(inner_html=inner_html, css_class=css_class)
        result = content.smart_dump()
        assert result == expected_output
        assert isinstance(result, dict)
