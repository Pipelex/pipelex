import html
import json
import re

from rich.markdown import Markdown
from rich.syntax import Syntax
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.pretty import PrettyPrintable

HTML_PATTERN = re.compile(r"^\s*<(!DOCTYPE|!--|[a-zA-Z])", re.IGNORECASE)


class TextContent(StuffContent):
    text: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some text ({len(self.text)} chars)"

    @override
    def rendered_plain(self) -> str:
        return self.text

    @override
    def rendered_html(self) -> str:
        # Always escape HTML special characters so text displays literally in browsers.
        # If you need to render trusted HTML content, use HtmlContent instead.
        return html.escape(self.text)

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self.text

    @override
    def rendered_json(self) -> str:
        return json.dumps({"text": self.text})

    def _looks_like_html(self) -> bool:
        """Check if the text content appears to be HTML."""
        return bool(HTML_PATTERN.match(self.text))

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        if self._looks_like_html():
            return Syntax(self.text, "html", word_wrap=True)
        return Markdown(self.text)
