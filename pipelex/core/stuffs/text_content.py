import json
from typing import Any

import markdown
from rich.markdown import Markdown
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.pretty import PrettyPrintable


class TextContent(StuffContent):
    text: str

    @override
    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return self.text

    @property
    @override
    def short_desc(self) -> str:
        return f"some text ({len(self.text)} chars)"

    @override
    def __str__(self) -> str:
        return self.text

    @override
    def rendered_plain(self) -> str:
        return self.text

    @override
    def rendered_html(self) -> str:
        # Convert a markdown string to HTML and return HTML as a Unicode string.
        return markdown.markdown(self.text)

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.text

    @override
    def rendered_json(self) -> str:
        return json.dumps({"text": self.text})

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        return Markdown(self.text)
