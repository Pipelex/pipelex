import json

from typing_extensions import override
from yattag import Doc

from pipelex.core.stuffs.stuff_content import StuffContent


class MermaidContent(StuffContent):
    mermaid_code: str
    mermaid_url: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some mermaid code ({len(self.mermaid_code)} chars)"

    @override
    def __str__(self) -> str:
        return self.mermaid_code

    @override
    def rendered_plain(self) -> str:
        return self.mermaid_code

    @override
    def rendered_html(self) -> str:
        doc, tag, text = Doc().tagtext()
        with tag("div", klass="mermaid"):
            text(self.mermaid_code)
        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.mermaid_code

    @override
    def rendered_json(self) -> str:
        return json.dumps({"mermaid": self.mermaid_code})
