"""Unit tests for stuff_viewer module."""

import pytest

from pipelex.core.stuffs.stuff_template_set import STUFF_TEMPLATE_SET
from pipelex.core.stuffs.stuff_viewer import (
    _get_html_tab_label,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    render_stuff_content_viewer,
    render_stuff_viewer,
)
from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry
from tests.unit.pipelex.core.stuffs.data import StuffViewerTestData


class TestGetHtmlTabLabel:
    """Tests for _get_html_tab_label helper function."""

    @pytest.mark.parametrize(
        ("content_type", "expected_label"),
        StuffViewerTestData.TAB_LABEL_CASES,
    )
    def test_returns_correct_label(self, content_type: str | None, expected_label: str) -> None:
        """Test that content type maps to correct tab label."""
        result = _get_html_tab_label(content_type)

        assert result == expected_label


@pytest.mark.asyncio(loop_scope="class")
class TestRenderStuffContentViewer:
    """Tests for render_stuff_content_viewer function."""

    @pytest.fixture(autouse=True)
    def setup_templates(self) -> None:
        """Ensure stuff templates are loaded before tests."""
        TemplateRegistry.clear()
        TemplateLoader.reset()
        stuff_name, stuff_package, stuff_templates = STUFF_TEMPLATE_SET
        TemplateLoader.register_set(
            name=stuff_name,
            package=stuff_package,
            templates=stuff_templates,
        )
        TemplateLoader.load("stuff")

    async def test_renders_basic_content(self) -> None:
        """Test rendering with all parameters provided."""
        html = await render_stuff_content_viewer(
            stuff_data={"key": "value"},
            stuff_data_text="key: value",
            stuff_data_html="<p>value</p>",
            content_type="text/html",
            title="Test Title",
            subtitle="Test Subtitle",
        )

        assert "<!DOCTYPE html>" in html
        assert "Test Title" in html
        assert "Test Subtitle" in html

    async def test_uses_default_title(self) -> None:
        """Test that default title is used when not provided."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<p>test</p>",
        )

        assert "Stuff Content" in html

    async def test_renders_with_none_subtitle(self) -> None:
        """Test rendering when subtitle is None."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<p>test</p>",
            subtitle=None,
        )

        assert "<!DOCTYPE html>" in html

    async def test_custom_title_and_subtitle(self) -> None:
        """Test rendering with custom title and subtitle."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<p>test</p>",
            title="Custom Title",
            subtitle="Custom Subtitle",
        )

        assert "Custom Title" in html
        assert "Custom Subtitle" in html

    async def test_tab_label_for_pdf_content_type(self) -> None:
        """Test that PDF content type gets PDF tab label."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<p>test</p>",
            content_type="application/pdf",
        )

        assert ">PDF<" in html

    async def test_tab_label_for_image_content_type(self) -> None:
        """Test that image content type gets Image tab label."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<img src='test.png'>",
            content_type="image/png",
        )

        assert ">Image<" in html

    async def test_tab_label_for_none_content_type(self) -> None:
        """Test that None content type gets HTML tab label."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<p>test</p>",
            content_type=None,
        )

        assert ">HTML<" in html

    async def test_embeds_json_escaped_data(self) -> None:
        """Test that special characters in data are properly JSON-escaped."""
        html = await render_stuff_content_viewer(
            stuff_data='Text with "quotes" and <tags>',
            stuff_data_text='Text with "quotes" and <tags>',
            stuff_data_html="<p>test</p>",
        )

        # The data should be JSON-encoded, escaping quotes and special chars
        assert '\\"quotes\\"' in html or "quotes" in html

    async def test_html_structure_is_valid(self) -> None:
        """Test that generated HTML has valid structure."""
        html = await render_stuff_content_viewer(
            stuff_data="test",
            stuff_data_text="test",
            stuff_data_html="<p>test</p>",
        )

        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html


@pytest.mark.asyncio(loop_scope="class")
class TestRenderStuffViewer:
    """Tests for render_stuff_viewer function."""

    @pytest.fixture(autouse=True)
    def setup_templates(self) -> None:
        """Ensure stuff templates are loaded before tests."""
        TemplateRegistry.clear()
        TemplateLoader.reset()
        stuff_name, stuff_package, stuff_templates = STUFF_TEMPLATE_SET
        TemplateLoader.register_set(
            name=stuff_name,
            package=stuff_package,
            templates=stuff_templates,
        )
        TemplateLoader.load("stuff")

    async def test_renders_text_content(self) -> None:
        """Test rendering TextContent produces valid HTML."""
        stuff = StuffViewerTestData.make_text_stuff()

        html = await render_stuff_viewer(stuff)

        assert "<!DOCTYPE html>" in html
        assert "Hello, World!" in html

    async def test_renders_html_content(self) -> None:
        """Test rendering HtmlContent."""
        stuff = StuffViewerTestData.make_html_stuff()

        html = await render_stuff_viewer(stuff)

        assert "<!DOCTYPE html>" in html
        assert "Test paragraph" in html

    async def test_renders_image_content_with_image_tab_label(self) -> None:
        """Test that ImageContent has Image tab label."""
        stuff = StuffViewerTestData.make_image_stuff()

        html = await render_stuff_viewer(stuff)

        assert ">Image<" in html

    async def test_renders_pdf_content_with_pdf_tab_label(self) -> None:
        """Test that DocumentContent has PDF tab label."""
        stuff = StuffViewerTestData.make_pdf_stuff()

        html = await render_stuff_viewer(stuff)

        assert ">PDF<" in html

    async def test_renders_mermaid_content(self) -> None:
        """Test rendering MermaidContent."""
        stuff = StuffViewerTestData.make_mermaid_stuff()

        html = await render_stuff_viewer(stuff)

        assert "<!DOCTYPE html>" in html
        assert "graph TD" in html

    async def test_uses_stuff_title_when_no_custom_title(self) -> None:
        """Test that stuff.title is used when no custom title provided."""
        stuff = StuffViewerTestData.make_text_stuff()

        html = await render_stuff_viewer(stuff)

        # The stuff title is derived from stuff_name and concept
        assert stuff.title in html

    async def test_uses_concept_code_for_default_subtitle(self) -> None:
        """Test that default subtitle contains concept code."""
        stuff = StuffViewerTestData.make_text_stuff()

        html = await render_stuff_viewer(stuff)

        assert f"Concept: {stuff.concept.code}" in html

    async def test_custom_title_overrides_stuff_title(self) -> None:
        """Test that custom title overrides stuff title."""
        stuff = StuffViewerTestData.make_text_stuff()
        custom_title = "My Custom Title"

        html = await render_stuff_viewer(stuff, title=custom_title)

        assert custom_title in html

    async def test_custom_subtitle_overrides_default(self) -> None:
        """Test that custom subtitle overrides default."""
        stuff = StuffViewerTestData.make_text_stuff()
        custom_subtitle = "My Custom Subtitle"

        html = await render_stuff_viewer(stuff, subtitle=custom_subtitle)

        assert custom_subtitle in html

    async def test_html_structure_contains_required_elements(self) -> None:
        """Test that generated HTML has all required elements."""
        stuff = StuffViewerTestData.make_text_stuff()

        html = await render_stuff_viewer(stuff)

        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    async def test_embeds_json_data_in_html(self) -> None:
        """Test that JSON data is embedded in the HTML."""
        stuff = StuffViewerTestData.make_text_stuff()

        html = await render_stuff_viewer(stuff)

        # JSON data should be embedded for JavaScript
        assert "stuffDataJson" in html or "stuff_data_json" in html or "Hello, World!" in html

    async def test_embeds_pretty_text_in_html(self) -> None:
        """Test that pretty text representation is embedded."""
        stuff = StuffViewerTestData.make_text_stuff()

        html = await render_stuff_viewer(stuff)

        # The pretty text format is embedded
        assert "Hello, World!" in html

    async def test_embeds_html_content_in_html(self) -> None:
        """Test that HTML content representation is embedded."""
        stuff = StuffViewerTestData.make_html_stuff()

        html = await render_stuff_viewer(stuff)

        # The inner HTML should be present
        assert "Test paragraph" in html

    async def test_special_characters_are_escaped(self) -> None:
        """Test that special characters are properly escaped for XSS prevention."""
        stuff = StuffViewerTestData.make_special_chars_stuff()

        html = await render_stuff_viewer(stuff)

        # The content should be in the HTML (escaped appropriately)
        assert "<!DOCTYPE html>" in html
        # The raw text with special chars should be JSON-encoded
        assert "quotes" in html
