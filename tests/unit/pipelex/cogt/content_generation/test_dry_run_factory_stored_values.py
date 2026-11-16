"""A mocked `Text`, `Markdown`, `Html` or `JSON` holds its value inline, and a user's structure that merely has the same field names keeps them.

A worker that runs a dry model call out of process has no class in hand, only the output's JSON schema, and rebuilds the
classes from it under the names the schema carries: a concept refining a stored-value class is rebuilt under the
concept's own name, with no base class and no validator. Its mock must still be one the real class accepts.
"""

import pytest
from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.dry_mock import build_mock_object, build_mock_objects
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import STORED_VALUE_REFERENCE_FIELDS, StoredValueContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


class Attachment(StructuredContent):
    """A user's structure whose fields happen to be named as a stored value's reference: it is no stored value."""

    url: str
    size: int
    mime_type: str
    preview: str
    title: str


class Excerpt(StructuredContent):
    """A user's structure named field for field as a stored text, but requiring them all: it is no stored value."""

    text: str
    url: str
    size: int
    mime_type: str
    preview: str


def _text_field_description(field_name: str) -> str | None:
    """The description `TextContent` gives a field, which the standard pins with the native `Text`."""
    return TextContent.model_fields[field_name].description


class Nullable(StructuredContent):
    """A user's structure named field for field as a stored text, all optional and nullable, but described as its own."""

    text: str | None = None
    url: str | None = None
    size: int | None = None
    mime_type: str | None = None
    preview: str | None = None


class Defaulted(StructuredContent):
    """A user's structure declared as a stored text's fields, descriptions included, but whose fields never hold None."""

    text: str = Field(default="", description=_text_field_description("text"))
    url: str = Field(default="", description=_text_field_description("url"))
    size: int = Field(default=0, description=_text_field_description("size"))
    mime_type: str = Field(default="", description=_text_field_description("mime_type"))
    preview: str = Field(default="", description=_text_field_description("preview"))


class Link(StructuredContent):
    """A user's structure declared as a stored text's reference, descriptions included, with no value field beside it."""

    url: str | None = Field(default=None, description=_text_field_description("url"))
    size: int | None = Field(default=None, description=_text_field_description("size"))
    mime_type: str | None = Field(default=None, description=_text_field_description("mime_type"))
    preview: str | None = Field(default=None, description=_text_field_description("preview"))


class AttachmentReport(StructuredContent):
    attachment: Attachment
    excerpt: Excerpt
    nullable: Nullable
    defaulted: Defaulted
    link: Link
    summary: TextContent


class _Wrapper(BaseModel):
    report: AttachmentReport


class Topic(TextContent):
    """A concept refining `Text`, as a concept with only a description does."""


class Headline(Topic):
    """A concept refining a refinement of `Text`."""


class Memo(MarkdownContent):
    """A concept refining `Markdown`."""


class Snippet(HtmlContent):
    """A concept refining `Html`."""


class Payload(JSONContent):
    """A concept refining `JSON`."""


class Briefing(StructuredContent):
    """A structure holding refinements of every stored-value class, at depth."""

    headline: Headline
    memos: list[Memo]
    snippet: Snippet
    payload: Payload


_STORED_VALUE_REFINEMENTS: list[type[StoredValueContent]] = [Topic, Headline, Memo, Snippet, Payload]
_STORED_VALUE_CLASSES: list[type[StoredValueContent]] = [TextContent, MarkdownContent, HtmlContent, JSONContent, *_STORED_VALUE_REFINEMENTS]


def _rebuild_from_schema(real_class: type[BaseModel]) -> type[BaseModel]:
    """Rebuild a class from its JSON schema as `resolve_object_class` does on a worker with no class in hand.

    The schema is the class's own, which keeps the referenced form's fields beside the value.
    """
    rebuilt_class = SchemaToModelFactory.make_from_json_schema(schema=real_class.model_json_schema(), class_name=real_class.__name__)
    assert not issubclass(rebuilt_class, StoredValueContent)
    return rebuilt_class


def _assert_holds_its_value_inline(content: StoredValueContent) -> None:
    assert content.require_value() is not None
    for field_name in STORED_VALUE_REFERENCE_FIELDS:
        assert getattr(content, field_name) is None
    assert content.is_loaded


class TestDryRunFactoryStoredValues:
    @pytest.mark.parametrize("stored_value_class", _STORED_VALUE_CLASSES)
    def test_a_mocked_stored_value_content_holds_its_value_inline(self, stored_value_class: type[StoredValueContent]) -> None:
        content = DryRunFactory.make_dry_run_factory(stored_value_class).build()

        _assert_holds_its_value_inline(content)

    @pytest.mark.parametrize("user_structure_class", [Attachment, Excerpt, Nullable, Defaulted, Link])
    @pytest.mark.parametrize("is_rebuilt", [False, True])
    def test_a_user_structure_with_reference_like_fields_keeps_them(self, user_structure_class: type[StructuredContent], is_rebuilt: bool) -> None:
        """A structure is no stored value unless it declares a stored value's fields as the native class does, each admitting None."""
        mock_class = _rebuild_from_schema(user_structure_class) if is_rebuilt else user_structure_class

        structure = user_structure_class.model_validate(build_mock_object(mock_class).model_dump(mode="json"))

        field_values = structure.model_dump()
        assert isinstance(field_values["url"], str)
        assert isinstance(field_values["size"], int)
        assert isinstance(field_values["mime_type"], str)
        assert isinstance(field_values["preview"], str)

    def test_a_nested_user_structure_with_reference_like_field_names_keeps_them_beside_an_inline_text(self) -> None:
        wrapper = build_mock_object(_Wrapper)

        assert isinstance(wrapper.report.attachment.url, str)
        assert isinstance(wrapper.report.attachment.preview, str)
        assert isinstance(wrapper.report.excerpt.url, str)
        assert wrapper.report.summary.url is None
        assert isinstance(wrapper.report.summary.text, str)

    def test_rebuilt_user_structures_keep_their_fields_beside_an_inline_text(self) -> None:
        """A rebuilt copy keeps no base class: a user's structure is told from a stored value by its fields, and keeps them."""
        rebuilt_class = _rebuild_from_schema(AttachmentReport)

        report = AttachmentReport.model_validate(build_mock_object(rebuilt_class).model_dump(mode="json"))

        assert isinstance(report.attachment.url, str)
        assert isinstance(report.attachment.size, int)
        assert isinstance(report.excerpt.url, str)
        assert isinstance(report.excerpt.text, str)
        assert isinstance(report.nullable.url, str)
        assert isinstance(report.defaulted.url, str)
        assert isinstance(report.link.url, str)
        _assert_holds_its_value_inline(report.summary)

    @pytest.mark.parametrize("stored_value_class", _STORED_VALUE_CLASSES)
    def test_a_rebuilt_stored_value_class_is_mocked_inline_whatever_its_name(self, stored_value_class: type[StoredValueContent]) -> None:
        """A native class or a refinement of one, at any depth, rebuilt under its own name, is mocked as a value the real class accepts."""
        rebuilt_class = _rebuild_from_schema(stored_value_class)

        content = stored_value_class.model_validate(build_mock_object(rebuilt_class).model_dump(mode="json"))

        _assert_holds_its_value_inline(content)

    @pytest.mark.parametrize("stored_value_class", _STORED_VALUE_CLASSES)
    def test_a_rebuilt_stored_value_class_is_mocked_inline_in_a_list(self, stored_value_class: type[StoredValueContent]) -> None:
        rebuilt_class = _rebuild_from_schema(stored_value_class)

        mocks = build_mock_objects(rebuilt_class, count=3)

        assert len(mocks) == 3
        for mock in mocks:
            _assert_holds_its_value_inline(stored_value_class.model_validate(mock.model_dump(mode="json")))

    def test_rebuilt_stored_value_refinements_nested_in_a_structure_are_mocked_inline(self) -> None:
        rebuilt_class = _rebuild_from_schema(Briefing)

        for mock in build_mock_objects(rebuilt_class, count=3):
            briefing = Briefing.model_validate(mock.model_dump(mode="json"))
            _assert_holds_its_value_inline(briefing.headline)
            for memo in briefing.memos:
                _assert_holds_its_value_inline(memo)
            _assert_holds_its_value_inline(briefing.snippet)
            _assert_holds_its_value_inline(briefing.payload)
