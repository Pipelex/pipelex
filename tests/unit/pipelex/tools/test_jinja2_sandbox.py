"""The template sandbox: templates read data and call methods of plain values, and nothing else.

Every refusal is a `Jinja2TemplateSecurityError` raised at the point of access; every legitimate shape
the templates of the workspace use renders as it did before the sandbox.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.exceptions import Jinja2TemplateRenderError, Jinja2TemplateSecurityError
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_sandbox import _MUTATING_METHOD_NAMES  # pyright: ignore[reportPrivateUsage]
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_TEMPLATING_STYLE = TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.PLAIN)


class _Mood(StrEnum):
    CALM = "calm"

    def shout(self) -> str:
        return self.value.upper()


def _make_artefact(*, content: StuffContent, name: str, concept_code: NativeConceptCode) -> StuffArtefact:
    return StuffArtefact(
        Stuff(
            stuff_code=f"{name}_code",
            stuff_name=name,
            concept=ConceptFactory.make_native_concept(native_concept_code=concept_code),
            content=content,
        )
    )


def _make_context(*, registry: ImageRegistry | None = None) -> dict[str, Any]:
    return {
        "note": _make_artefact(content=TextContent(text="hello"), name="note", concept_code=NativeConceptCode.TEXT),
        "photo": _make_artefact(content=ImageContent(url="https://example.com/photo.png"), name="photo", concept_code=NativeConceptCode.IMAGE),
        # A list input hands a template its items, which are content objects: the route to a pydantic method.
        "photos": _make_artefact(
            content=ListContent[ImageContent](items=[ImageContent(url="https://example.com/photo.png")]),
            name="photos",
            concept_code=NativeConceptCode.IMAGE,
        ),
        "created_at": datetime(2026, 1, 2, 3, 4, 5),
        "record": {"a": 1, "b": 2},
        "keyed": {"_id": "abc123", "__typename": "User"},
        "tags": {"a", "b"},
        "mood": _Mood.CALM,
        Jinja2ContextKey.IMAGE_REGISTRY: registry or ImageRegistry(),
    }


async def _render(template_source: str, *, context: dict[str, Any] | None = None) -> str:
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.LLM_PROMPT,
        templating_context=context or _make_context(),
        templating_style=_TEMPLATING_STYLE,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestTemplateSandboxRefusals:
    @pytest.mark.parametrize(
        ("topic", "template_source"),
        [
            ("globals_escape", "{{ cycler.__init__.__globals__ }}"),
            ("raw_stuff_by_bracket", "{{ note['_stuff'] }}"),
            ("class_by_bracket", "{{ note['__class__'] }}"),
            ("raw_content_by_bracket", "{{ note['_content'] }}"),
            ("raw_content_by_dot", "{{ note._content }}"),
            ("raw_stuff_by_dot", "{{ note._stuff }}"),
            ("raw_stuff_by_attr_filter", "{{ note | attr('_stuff') }}"),
            ("pydantic_constructor", "{{ photos[0].model_validate({'url': 'pipelex-storage://org-b/x.png'}) }}"),
            ("pydantic_copy", "{{ photos[0].model_copy() }}"),
            ("pydantic_dump", "{{ photos[0].model_dump() }}"),
            ("artefact_undeclared_method", "{{ note.render_for_tag_async() }}"),
            ("class_method_through_instance", "{{ created_at.now() }}"),
            ("mutating_list_method", "{% set items = [1] %}{{ items.append(2) }}"),
            ("mutating_dict_method", "{{ record.update({'c': 3}) }}"),
            ("mutating_set_method_jinja_misses", "{{ tags.intersection_update(['a']) }}"),
            ("format_string_dunder", "{{ '{0.__class__}'.format(note) }}"),
            ("format_string_private_attribute", "{{ '{0._stuff}'.format(note) }}"),
            ("format_string_private_item", "{{ '{0[_stuff]}'.format(note) }}"),
            ("subclass_method_on_plain_value", "{{ mood.shout() }}"),
            ("private_name_on_plain_dict", "{{ record._secret }}"),
            ("private_key_by_dot_on_plain_dict", "{{ keyed._id }}"),
            ("dunder_by_bracket_on_plain_dict", "{{ record['__class__'] }}"),
        ],
    )
    async def test_refused(self, topic: str, template_source: str) -> None:
        with pytest.raises(Jinja2TemplateSecurityError) as exc_info:
            await _render(template_source)
        # The message names what was refused, never the template source.
        assert template_source not in str(exc_info.value), topic

    async def test_forged_image_never_reaches_the_registry(self) -> None:
        """The attack the stock sandbox let through: a template forging an image pointing at a foreign storage key."""
        registry = ImageRegistry()
        template_source = "{{ photos[0].model_validate({'url': 'pipelex-storage:/' ~ '/org-b/x.png'}) | with_images }}"
        with pytest.raises(Jinja2TemplateSecurityError):
            await _render(template_source, context=_make_context(registry=registry))
        assert registry.images == []

    async def test_refusal_names_the_attribute_and_the_type(self) -> None:
        with pytest.raises(Jinja2TemplateSecurityError, match=r"may not read '_stuff' on a 'StuffArtefact' value"):
            await _render("{{ note._stuff }}")

    async def test_refusal_names_the_callable_and_the_type(self) -> None:
        with pytest.raises(Jinja2TemplateSecurityError, match=r"may not call the method 'model_copy' of a 'ImageContent' value"):
            await _render("{{ photos[0].model_copy() }}")

    async def test_refused_mutation_leaves_the_value_unchanged(self) -> None:
        context = _make_context()
        with pytest.raises(Jinja2TemplateSecurityError):
            await _render("{{ tags.intersection_update(['a']) }}", context=context)
        assert context["tags"] == {"a", "b"}

    async def test_wrapped_stuff_is_not_readable(self) -> None:
        """An artefact exposes its content's fields and its metadata, never the Stuff it wraps."""
        with pytest.raises(Jinja2TemplateRenderError, match="undefined error"):
            await _render("{{ note.stuff.content }}")

    async def test_method_template_cannot_include(self) -> None:
        """A method template renders without a loader, so it cannot reach Pipelex's registered templates."""
        with pytest.raises(Jinja2TemplateRenderError, match="template not found"):
            await _render("{% include 'stuff_viewer.html.jinja2' %}")

    async def test_calling_an_undefined_name_stays_an_undefined_error(self) -> None:
        with pytest.raises(Jinja2TemplateRenderError, match="undefined error"):
            await _render("{{ nowhere() }}")


class TestTemplateSandboxSyncRender:
    def test_sync_render_refuses_too(self) -> None:
        with pytest.raises(Jinja2TemplateSecurityError):
            render_jinja2_sync(
                template_source="{{ note['_stuff'] }}",
                template_category=TemplateCategory.BASIC,
                templating_context=_make_context(),
            )

    def test_sync_render_reads_metadata(self) -> None:
        rendered = render_jinja2_sync(
            template_source="{{ note._stuff_name }}: {{ note.text }}",
            template_category=TemplateCategory.BASIC,
            templating_context=_make_context(),
        )
        assert rendered == "note: hello"


@pytest.mark.asyncio(loop_scope="class")
class TestTemplateSandboxLegitimateShapes:
    @pytest.mark.parametrize(
        ("topic", "template_source", "expected"),
        [
            (
                "metadata_by_dot",
                "{{ note._stuff_name }}|{{ note._content_class }}|{{ note._concept_code }}|{{ note._stuff_code }}",
                "note|TextContent|Text|note_code",
            ),
            (
                "metadata_by_bracket",
                "{{ note['_stuff_name'] }}|{{ note['_content_class'] }}|{{ note['_concept_code'] }}|{{ note['_stuff_code'] }}",
                "note|TextContent|Text|note_code",
            ),
            ("content_fields", "{{ note.text }}|{{ note['text'] }}|{{ photo.url }}", "hello|hello|https://example.com/photo.png"),
            ("artefact_get", "{{ note.get('text') }}|{{ note.get('missing', default='fallback') }}", "hello|fallback"),
            ("artefact_get_refuses_attributes", "{{ note.get('_stuff') }}|{{ note.get('stuff') }}", "None|None"),
            ("artefact_iter_keys_and_values", "{{ note.iter_keys() | list | length }}/{{ note.iter_values() | list | length }}", "5/5"),
            (
                "date_methods",
                "{{ created_at.isoformat() }}|{{ created_at.strftime('%Y') }}|{{ created_at.toordinal() }}",
                "2026-01-02T03:04:05|2026|739618",
            ),
            ("dict_methods", "{{ record.get('a') }}|{{ record.items() | list | length }}|{{ record.keys() | list | join(',') }}", "1|2|a,b"),
            ("private_keys_of_a_plain_dict_by_bracket", "{{ keyed['_id'] }}|{{ keyed['__typename'] }}", "abc123|User"),
            ("set_methods", "{{ tags.intersection(['a']) | list | join }}|{{ tags.issuperset(['a']) }}", "a|True"),
            ("list_input_items", "{{ photos[0].url }}|{{ photos | length }}", "https://example.com/photo.png|1"),
            ("string_methods", "{{ 'abc'.upper() }}|{{ 'a,b'.split(',') | join('-') }}|{{ ', '.join(['x', 'y']) }}", "ABC|a-b|x, y"),
            ("plain_method_on_plain_subclass", "{{ mood.upper() }}", "CALM"),
            ("loop_helpers", "{% for i in [1, 2, 3] %}{{ loop.cycle('o', 'e') }}{% endfor %}", "oeo"),
            ("loop_changed", "{% for i in [1, 1, 2] %}{{ loop.changed(i) }};{% endfor %}", "True;False;True;"),
            ("namespace", "{% set ns = namespace(total=0) %}{% for i in [1, 2] %}{% set ns.total = ns.total + i %}{% endfor %}{{ ns.total }}", "3"),
            ("cycler_and_joiner", "{% set c = cycler('a', 'b') %}{{ c.next() }}{{ c.next() }}{% set j = joiner(',') %}{{ j() }}x{{ j() }}y", "abx,y"),
            ("macro_with_caller", "{% macro wrap(x) %}[{{ x }}{{ caller() }}]{% endmacro %}{% call wrap(1) %}C{% endcall %}", "[1C]"),
            ("dict_global_and_range", "{{ dict(a=1)['a'] }}|{{ range(3) | list | length }}", "1|3"),
            ("str_format", "{{ '{0} {1}'.format('a', 2) }}|{{ '{0.text}'.format(note) }}", "a 2|hello"),
            ("tag_filter", "{{ note | tag }}", "<note>\nhello\n</note>"),
            ("format_filter", "{{ note | format }}", "hello"),
            ("with_images_filter", "{{ photo | with_images }}", "[Image 1]"),
            (
                "builtin_filters",
                "{{ [1, 2] | length }}|{{ record | tojson }}|{{ [note] | map(attribute='text') | join }}",
                '2|{"a": 1, "b": 2}|hello',
            ),
        ],
    )
    async def test_renders(self, topic: str, template_source: str, expected: str) -> None:
        rendered = await _render(template_source)
        assert rendered == expected, topic

    async def test_iter_items_yields_fields_and_metadata_without_the_raw_content(self) -> None:
        rendered = await _render("{% for key, value in note.iter_items() %}{{ key }}={{ value }};{% endfor %}")
        assert rendered == "text=hello;_stuff_name=note;_content_class=TextContent;_concept_code=Text;_stuff_code=note_code;"

    async def test_html_template_formats_markup_through_the_escaping_formatter(self) -> None:
        rendered = await render_jinja2_async(
            template_source="{{ ('<b>{0}</b>' | safe).format('<i>') }}",
            template_category=TemplateCategory.HTML,
            templating_context={},
        )
        assert rendered == "<b>&lt;i&gt;</b>"


# The methods of each mutable plain type that leave the value unchanged, so that together with the
# sandbox's own list of mutating methods they classify every public method the type has.
_NON_MUTATING_METHOD_NAMES: dict[type, frozenset[str]] = {
    list: frozenset({"copy", "count", "index"}),
    dict: frozenset({"copy", "fromkeys", "get", "items", "keys", "values"}),
    set: frozenset({"copy", "difference", "intersection", "isdisjoint", "issubset", "issuperset", "symmetric_difference", "union"}),
}


class TestMutatingMethodList:
    @pytest.mark.parametrize("plain_type", [list, dict, set])
    def test_every_public_method_is_classified(self, plain_type: type) -> None:
        """A method a later Python adds fails here until someone decides whether it mutates."""
        public_names = {name for name in dir(plain_type) if not name.startswith("_")}
        mutating = _MUTATING_METHOD_NAMES[plain_type]
        non_mutating = _NON_MUTATING_METHOD_NAMES[plain_type]
        assert not mutating & non_mutating
        assert public_names == mutating | non_mutating
