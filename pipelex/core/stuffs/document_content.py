from pydantic import Field, model_validator
from rich.text import Text
from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.misc.http_utils import validate_url_resource_exists
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.uri.uri_resolver import extract_filename_from_uri, resolve_uri
from pipelex.types import Self


class DocumentContent(StuffContent):
    url: str = Field(..., description="The document URL: pipelex storage URL, HTTP/HTTPS URL, or base64 data URL")

    public_url: str | None = Field(default=None, description="The public HTTPS URL of the document")
    mime_type: str | None = Field(default=None, description="The MIME type of the document")
    filename: str | None = Field(default=None, description="The original filename of the document")
    title: str | None = Field(default=None, description="The title of the document or source")
    snippet: str | None = Field(default=None, description="A text snippet or excerpt from the document")

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
        return self.mime_type

    @property
    @override
    def short_desc(self) -> str:
        if self.title:
            return f"document: {self.title}"
        url_desc = resolve_uri(self.url).kind.desc
        return f"{url_desc} of a document"

    @override
    def rendered_plain(self) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"- {self.title}: {self.url}")
        else:
            parts.append(self.url)
        if self.snippet:
            parts.append(f"  {self.snippet}")
        return "\n".join(parts)

    @override
    def rendered_html(self) -> str:
        display_text = self.title or self.public_url or self.url
        # The |e filter escapes HTML special characters to prevent XSS attacks
        template_source = '<a href="{{ url|e }}" class="msg-document">{{ display_text|e }}</a>'
        if self.snippet:
            template_source += "<br/><small>{{ snippet|e }}</small>"
        context: dict[str, str] = {
            "url": self.public_url or self.url,
            "display_text": display_text,
        }
        if self.snippet:
            context["snippet"] = self.snippet
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context=context,
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        display_text = self.title or self.public_url or self.url
        result = f"[{display_text}]({self.public_url or self.url})"
        if self.snippet:
            result += f"\n  {self.snippet}"
        return result

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        source_text = Text()
        if self.title:
            source_text.append(self.title, style="bold")
            source_text.append(f" ({self.url})", style="dim cyan")
        else:
            source_text.append(self.url, style="dim cyan")
        if self.snippet:
            source_text.append(f"\n  {self.snippet}", style="dim italic")
        return source_text
