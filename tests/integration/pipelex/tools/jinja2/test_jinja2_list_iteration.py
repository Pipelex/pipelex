"""Integration tests for direct ListContent iteration in Jinja2 templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_artefact import StuffArtefact


def _make_list_artefact(texts: list[str]) -> StuffArtefact:
    """Create a StuffArtefact wrapping ListContent of TextContent items."""
    items = [TextContent(text=text) for text in texts]
    stuff = Stuff(
        stuff_code="test_list",
        stuff_name="my_list",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=ListContent(items=items),
    )
    return stuff.make_artefact()


class TestJinja2ListIteration:
    """Tests for direct iteration over ListContent in Jinja2 templates."""

    def test_direct_iteration_in_template(self) -> None:
        """Verify that {% for item in list_stuff %} works directly."""
        artefact = _make_list_artefact(["Apple", "Banana", "Cherry"])
        template = "{% for item in my_list %}{{ item.text }}, {% endfor %}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "Apple, Banana, Cherry, "

    def test_direct_iteration_with_loop_index(self) -> None:
        """Verify that loop.index works with direct iteration."""
        artefact = _make_list_artefact(["First", "Second", "Third"])
        template = "{% for item in my_list %}{{ loop.index }}. {{ item.text }}\n{% endfor %}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "1. First\n2. Second\n3. Third\n"

    def test_backward_compatible_items_iteration(self) -> None:
        """Verify that {% for item in list_stuff.items %} still works."""
        artefact = _make_list_artefact(["Apple", "Banana"])
        template = "{% for item in my_list.items %}{{ item.text }}, {% endfor %}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "Apple, Banana, "

    def test_len_filter_in_template(self) -> None:
        """Verify that {{ list_stuff | length }} works."""
        artefact = _make_list_artefact(["A", "B", "C", "D"])
        template = "Count: {{ my_list | length }}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "Count: 4"

    def test_index_access_in_template(self) -> None:
        """Verify that {{ list_stuff[0] }} works for index access."""
        artefact = _make_list_artefact(["First", "Second", "Third"])
        template = "First item: {{ my_list[0].text }}, Last item: {{ my_list[-1].text }}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "First item: First, Last item: Third"

    def test_empty_list_iteration(self) -> None:
        """Verify that iterating over empty list works."""
        artefact = _make_list_artefact([])
        template = "Items: {% for item in my_list %}{{ item.text }}{% else %}None{% endfor %}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "Items: None"

    def test_conditional_with_length(self) -> None:
        """Verify that conditional checks with length work."""
        artefact = _make_list_artefact(["A", "B"])
        template = "{% if my_list | length > 0 %}Has items{% else %}Empty{% endif %}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        assert result == "Has items"

    def test_first_and_last_filters(self) -> None:
        """Verify that Jinja2 first/last filters work with direct iteration."""
        artefact = _make_list_artefact(["Alpha", "Beta", "Gamma"])
        template = "First: {{ my_list | first }}, Last: {{ my_list | last }}"

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
        )

        # first/last will return TextContent objects, which render as their repr
        assert "Alpha" in result
        assert "Gamma" in result

    def test_iteration_with_templating_style(self) -> None:
        """Verify that iteration works with templating style applied."""
        artefact = _make_list_artefact(["Item 1", "Item 2"])
        template = "{% for item in my_list %}- {{ item.text }}\n{% endfor %}"
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        result = render_jinja2_sync(
            template_source=template,
            template_category=TemplateCategory.LLM_PROMPT,
            templating_context={"my_list": artefact},
            templating_style=templating_style,
        )

        assert result == "- Item 1\n- Item 2\n"
