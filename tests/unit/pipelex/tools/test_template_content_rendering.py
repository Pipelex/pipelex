"""Unit tests for template content rendering.

Tests that StuffArtefact and StuffContent render properly in Jinja2 templates
using the __str__ method, ensuring users see actual content rather than
object representations like 'StuffArtefact(name)'.
"""

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat


def _make_text_stuff(text: str, name: str = "test_text") -> Stuff:
    """Create a Stuff with TextContent."""
    return Stuff(
        stuff_code=f"{name}_code",
        stuff_name=name,
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text=text),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestTemplateContentRendering:
    """Tests that template rendering produces actual content, not object representations."""

    async def test_stuff_artefact_str_returns_content(self) -> None:
        """Test that str(StuffArtefact) returns the actual content, not repr."""
        stuff = _make_text_stuff("Hello, World!")
        artefact = StuffArtefact(stuff)

        result = str(artefact)

        assert result == "Hello, World!"
        assert "StuffArtefact" not in result

    async def test_stuff_content_str_returns_content(self) -> None:
        """Test that str(StuffContent) returns the actual content, not repr."""
        content = TextContent(text="Hello, World!")

        result = str(content)

        assert result == "Hello, World!"
        assert "TextContent" not in result

    async def test_template_direct_interpolation_renders_content(self) -> None:
        """Test that {{ variable }} renders content, not object representation."""
        stuff = _make_text_stuff("Hello from template!")
        artefact = StuffArtefact(stuff)

        template = "Message: {{ my_content }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Hello from template!" in result
        assert "StuffArtefact" not in result

    async def test_template_format_filter_renders_content(self) -> None:
        """Test that {{ variable | format }} renders actual content."""
        stuff = _make_text_stuff("Formatted content here")
        artefact = StuffArtefact(stuff)

        template = "Formatted: {{ my_content | format }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Formatted content here" in result
        assert "StuffArtefact" not in result

    async def test_template_tag_filter_renders_content(self) -> None:
        """Test that {{ variable | tag }} renders actual content with tags."""
        stuff = _make_text_stuff("Tagged content", name="my_stuff")
        artefact = StuffArtefact(stuff)

        template = "{{ my_content | tag }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.TICKS,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Tagged content" in result
        assert "my_stuff" in result  # Tag name from stuff_name
        assert "```" in result  # TICKS style
        assert "StuffArtefact" not in result

    async def test_template_tag_filter_with_custom_name(self) -> None:
        """Test that {{ variable | tag("custom") }} uses custom tag name."""
        stuff = _make_text_stuff("Custom tagged content")
        artefact = StuffArtefact(stuff)

        template = "{{ my_content | tag('custom_tag') }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.XML,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Custom tagged content" in result
        assert "<custom_tag>" in result
        assert "</custom_tag>" in result
        assert "StuffArtefact" not in result

    async def test_template_format_then_tag(self) -> None:
        """Test chained filters: {{ variable | format | tag }}."""
        stuff = _make_text_stuff("Chained filter content", name="chained")
        artefact = StuffArtefact(stuff)

        template = "{{ my_content | format | tag }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.TICKS,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Chained filter content" in result
        assert "```" in result
        assert "StuffArtefact" not in result

    async def test_template_multiline_content(self) -> None:
        """Test that multiline content renders correctly."""
        multiline_text = """Line 1
Line 2
Line 3"""
        stuff = _make_text_stuff(multiline_text)
        artefact = StuffArtefact(stuff)

        template = "Content:\n{{ my_content }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        assert "StuffArtefact" not in result

    async def test_template_special_characters_in_content(self) -> None:
        """Test that special characters are preserved in template rendering."""
        special_text = "Special chars: <>&\"' and unicode: \u00e9\u00e8\u00e0"
        stuff = _make_text_stuff(special_text)
        artefact = StuffArtefact(stuff)

        template = "{{ my_content }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        # In plain text mode, special characters should be preserved
        assert "\u00e9\u00e8\u00e0" in result
        assert "StuffArtefact" not in result

    async def test_multiple_artefacts_in_template(self) -> None:
        """Test multiple StuffArtefacts in a single template."""
        stuff1 = _make_text_stuff("First content", name="first")
        stuff2 = _make_text_stuff("Second content", name="second")
        artefact1 = StuffArtefact(stuff1)
        artefact2 = StuffArtefact(stuff2)

        template = "A: {{ first }}\nB: {{ second }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"first": artefact1, "second": artefact2},
            template_source=template,
            templating_style=templating_style,
        )

        assert "First content" in result
        assert "Second content" in result
        assert "StuffArtefact" not in result

    async def test_format_json_renders_json(self) -> None:
        """Test that format('json') renders actual JSON content."""
        stuff = _make_text_stuff("JSON test content")
        artefact = StuffArtefact(stuff)

        template = "{{ my_content | format('json') }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        # TextContent.rendered_json returns {"text": "..."}
        assert "JSON test content" in result
        assert "text" in result
        assert "StuffArtefact" not in result

    async def test_format_markdown_renders_markdown(self) -> None:
        """Test that format('markdown') renders markdown content."""
        stuff = _make_text_stuff("Markdown **bold** content")
        artefact = StuffArtefact(stuff)

        template = "{{ my_content | format('markdown') }}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )

        result: str = await render_jinja2_async(
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_content": artefact},
            template_source=template,
            templating_style=templating_style,
        )

        assert "Markdown **bold** content" in result
        assert "StuffArtefact" not in result
