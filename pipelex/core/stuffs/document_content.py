from pydantic import Field, model_validator
from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.misc.http_utils import validate_url_resource_exists
from pipelex.tools.uri.uri_resolver import extract_filename_from_uri, resolve_uri
from pipelex.types import Self


class DocumentContent(StuffContent):
    url: str = Field(..., description="The document URL: pipelex storage URL, HTTP/HTTPS URL, or base64 data URL")

    public_url: str | None = Field(default=None, description="The public HTTPS URL of the document")
    mime_type: str | None = Field(default=None, description="The MIME type of the document")
    filename: str | None = Field(default=None, description="The original filename of the document")

    @model_validator(mode="after")
    def _auto_populate_filename(self) -> Self:
        """Auto-populate filename from url when it is a local file path."""
        if self.filename is None:
            self.filename = extract_filename_from_uri(self.url)
        return self

    @override
    def validate_resources(self) -> None:
        validate_url_resource_exists(self.url)

    @property
    @override
    def content_type(self) -> str | None:
        return self.mime_type or "application/pdf"

    @property
    @override
    def short_desc(self) -> str:
        url_desc = resolve_uri(self.url).kind.desc
        return f"{url_desc} of a document"

    @override
    def rendered_plain(self) -> str:
        return self.url

    @override
    def rendered_html(self) -> str:
        # The |e filter escapes HTML special characters to prevent XSS attacks
        template_source = '<a href="{{ url|e }}" class="msg-document">{{ display_text|e }}</a>'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "url": self.public_url or self.url,
                "display_text": self.public_url or self.url,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        display_text = self.public_url or self.url
        return f"[{display_text}]({self.url})"
