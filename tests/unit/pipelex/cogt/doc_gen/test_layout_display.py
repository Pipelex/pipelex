import pytest

from pipelex.cogt.doc_gen.layout_display import display_scalar, is_numeric_column, markdown_as_html
from pipelex.cogt.doc_gen.layout_tree import LayoutScalar
from tests.unit.pipelex.cogt.doc_gen.test_data import LayoutDisplayTestData


class TestLayoutDisplay:
    @pytest.mark.parametrize(("value", "expected"), LayoutDisplayTestData.SCALAR_CASES)
    def test_a_scalar_prints_plainly(self, value: LayoutScalar, expected: str) -> None:
        assert display_scalar(value=value) == expected

    @pytest.mark.parametrize(("topic", "values", "expected"), LayoutDisplayTestData.NUMERIC_COLUMN_CASES)
    def test_a_column_is_numeric_when_it_holds_numbers_only(self, topic: str, values: list[LayoutScalar], expected: bool) -> None:
        assert is_numeric_column(values=values) is expected, topic

    def test_raw_html_in_markdown_comes_out_escaped(self) -> None:
        html = markdown_as_html(markdown='Before <script>alert("x")</script> after.\n\n<div onclick="steal()">block</div>')
        assert "<script>" not in html
        assert "<div" not in html
        assert "&lt;script&gt;" in html
        assert "&lt;div onclick=" in html

    def test_a_table_and_a_strikethrough_are_formatted(self) -> None:
        html = markdown_as_html(markdown="| Item | Qty |\n| - | - |\n| Tea | 2 |\n\n~~withdrawn~~")
        assert "<table>" in html
        assert "<th>Item</th>" in html
        assert "<td>Tea</td>" in html
        assert "<s>withdrawn</s>" in html

    def test_only_a_url_with_a_scheme_becomes_a_link(self) -> None:
        html = markdown_as_html(markdown="See https://pipelex.com, README.md, www.example.com and ada@example.com.")
        assert '<a href="https://pipelex.com">https://pipelex.com</a>' in html
        assert html.count("<a ") == 1
        assert "README.md" in html
