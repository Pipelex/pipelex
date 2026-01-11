"""Integration tests for stuff_viewer module.

These tests verify end-to-end HTML viewer rendering with real templates
and the Pipelex framework fully initialized.
"""

import pytest
from pydantic import Field

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_template_set import STUFF_TEMPLATE_SET
from pipelex.core.stuffs.stuff_viewer import render_stuff_viewer
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry


class SampleDataModel(StructuredContent):
    """Structured content model for integration tests."""

    title: str = Field(description="Sample title")
    value: int = Field(description="Sample value")
    description: str = Field(description="Sample description")


@pytest.mark.asyncio(loop_scope="class")
class TestStuffViewerIntegration:
    """Integration tests for render_stuff_viewer with full framework."""

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

    async def test_full_rendering_pipeline_text_content(self) -> None:
        """Test complete rendering pipeline with TextContent."""
        text_content = TextContent(text="This is a test message for integration testing.")
        stuff = Stuff(
            stuff_code="integ1",
            stuff_name="integration_test_text",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=text_content,
        )

        html = await render_stuff_viewer(stuff)

        # Verify the complete rendering pipeline works
        assert "<!DOCTYPE html>" in html
        assert "integration_test_text" in html or "Text" in html
        assert "This is a test message" in html

    async def test_full_rendering_pipeline_structured_content(self) -> None:
        """Test complete rendering pipeline with StructuredContent."""
        structured_content = SampleDataModel(
            title="Test Item",
            value=42,
            description="A test item for integration testing",
        )
        stuff = Stuff(
            stuff_code="integ2",
            stuff_name="integration_test_structured",
            concept=ConceptFactory.make(
                concept_code="SampleDataModel",
                domain_code="test_domain",
                description="Test structured content",
                structure_class_name="SampleDataModel",
            ),
            content=structured_content,
        )

        html = await render_stuff_viewer(stuff)

        # Verify structured data is rendered
        assert "<!DOCTYPE html>" in html
        assert "Test Item" in html
        assert "42" in html

    async def test_html_contains_format_toolbar(self) -> None:
        """Test that rendered HTML contains format toolbar with tabs."""
        stuff = Stuff(
            stuff_code="integ3",
            stuff_name="toolbar_test",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="Toolbar test"),
        )

        html = await render_stuff_viewer(stuff)

        # Check for format tab elements
        assert "format-tabs" in html or "tab" in html.lower()
        assert ">HTML<" in html or ">JSON<" in html or ">Pretty<" in html

    async def test_html_contains_action_buttons(self) -> None:
        """Test that rendered HTML contains action buttons."""
        stuff = Stuff(
            stuff_code="integ4",
            stuff_name="buttons_test",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="Buttons test"),
        )

        html = await render_stuff_viewer(stuff)

        # Check for action button elements (copy, download, etc.)
        assert "copy" in html.lower() or "download" in html.lower() or "action" in html.lower()

    async def test_rendered_html_well_formed(self) -> None:
        """Test that rendered HTML is well-formed with all required elements."""
        stuff = Stuff(
            stuff_code="integ5",
            stuff_name="structure_test",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="Structure test"),
        )

        html = await render_stuff_viewer(stuff)

        # Verify HTML structure
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body>" in html
        assert "</body>" in html
        assert "<title>" in html
        assert "</title>" in html

        # Verify head contains required elements
        assert "<style" in html or "css" in html.lower()
        assert "<script" in html

        # Verify basic nesting (head before body)
        head_pos = html.find("<head>")
        body_pos = html.find("<body>")
        assert head_pos < body_pos
