import html
import json
import re
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, PrivateAttr
from typing_extensions import override

from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.tools.misc.pretty import require_rich_for_rendering

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable

HTML_PATTERN = re.compile(r"^\s*<(!DOCTYPE|!--|[a-zA-Z])", re.IGNORECASE)


class TextContent(StoredValueContent):
    """A text"""

    value_field_name: ClassVar[str] = "text"
    value_form_field_names: ClassVar[tuple[str, ...]] = ("text",)
    value_kind_desc: ClassVar[str] = "text"

    text: str | None = Field(default=None, description="The text")
    url: str | None = Field(default=None, description="The URL of the stored text: a storage URI, an HTTP(S) URL, or a base64 data URL")
    size: int | None = Field(default=None, description="The length of the stored text, in bytes as stored")
    mime_type: str | None = Field(default=None, description="The MIME type of the stored text: text/plain or text/markdown")
    preview: str | None = Field(default=None, description="The first few hundred characters of the stored text, always its true start")

    # The text read from storage for a referenced content, never serialized.
    _loaded_text: str | None = PrivateAttr(default=None)

    @override
    def _has_loaded_value(self) -> bool:
        return self._loaded_text is not None

    @override
    def accept_loaded_text(self, *, text: str) -> None:
        if self.url is None:
            return
        self._loaded_text = text

    @override
    def require_value(self) -> str:
        return self.require_text()

    def require_text(self) -> str:
        """The text, held inline or loaded from storage.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its text that was never loaded.
        """
        if self.text is not None:
            return self.text
        if self._loaded_text is not None:
            return self._loaded_text
        raise self._make_not_loaded_error()

    @property
    @override
    def short_desc(self) -> str:
        if self.text is None:
            return self._stored_short_desc()
        return f"some text ({len(self.text)} chars)"

    @override
    def rendered_plain(self) -> str:
        return self.require_text()

    @override
    def rendered_html(self) -> str:
        # Always escape HTML special characters so text displays literally in browsers.
        # If you need to render trusted HTML content, use HtmlContent instead.
        return html.escape(self.require_text())

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self.require_text()

    @override
    def rendered_json(self) -> str:
        return json.dumps({"text": self.require_text()})

    def _looks_like_html(self) -> bool:
        """Check if the text content appears to be HTML."""
        return bool(HTML_PATTERN.match(self.require_text()))

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        text = self.require_text()
        require_rich_for_rendering()
        from rich.markdown import Markdown
        from rich.syntax import Syntax

        if self._looks_like_html():
            return Syntax(text, "html", word_wrap=True)
        return Markdown(text)
