"""A mocked `Text`, `Html` or `JSON` holds its value inline, and a user's structure that merely has the same field names keeps them."""

from pydantic import BaseModel

from pipelex.cogt.content_generation.dry_mock import build_mock_object
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


class Attachment(StructuredContent):
    """A user's structure whose fields happen to be named as a stored value's reference: it is no stored value."""

    url: str
    size: int
    mime_type: str
    preview: str
    title: str


class AttachmentReport(StructuredContent):
    attachment: Attachment
    summary: TextContent


class _Wrapper(BaseModel):
    report: AttachmentReport


class TestDryRunFactoryStoredValues:
    def test_a_mocked_stored_value_content_holds_its_value_inline(self) -> None:
        text = DryRunFactory.make_dry_run_factory(TextContent).build()
        markdown = DryRunFactory.make_dry_run_factory(MarkdownContent).build()
        html = DryRunFactory.make_dry_run_factory(HtmlContent).build()
        json_content = DryRunFactory.make_dry_run_factory(JSONContent).build()

        for content in (text, markdown, html, json_content):
            assert content.url is None
            assert content.size is None
            assert content.mime_type is None
            assert content.preview is None
            assert content.is_loaded

    def test_a_user_structure_with_reference_like_field_names_keeps_them(self) -> None:
        attachment = build_mock_object(Attachment)

        assert isinstance(attachment.url, str)
        assert isinstance(attachment.size, int)
        assert isinstance(attachment.mime_type, str)
        assert isinstance(attachment.preview, str)

    def test_a_nested_user_structure_with_reference_like_field_names_keeps_them_beside_an_inline_text(self) -> None:
        wrapper = build_mock_object(_Wrapper)

        assert isinstance(wrapper.report.attachment.url, str)
        assert isinstance(wrapper.report.attachment.preview, str)
        assert wrapper.report.summary.url is None
        assert isinstance(wrapper.report.summary.text, str)

    def test_classes_rebuilt_from_a_json_schema_are_told_apart_by_name(self) -> None:
        """A rebuilt copy keeps no base class: a stored value is told by its class name, a user's structure keeps its fields."""
        rebuilt_class = SchemaToModelFactory.make_from_json_schema(schema=AttachmentReport.model_json_schema(), class_name="AttachmentReport")

        report = AttachmentReport.model_validate(build_mock_object(rebuilt_class).model_dump(mode="json"))

        assert isinstance(report.attachment.url, str)
        assert isinstance(report.attachment.size, int)
        assert report.summary.url is None
        assert isinstance(report.summary.text, str)
