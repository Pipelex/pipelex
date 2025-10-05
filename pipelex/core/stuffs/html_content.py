import json

from typing_extensions import override
from yattag import Doc

from pipelex.core.stuffs.stuff_content import StuffContent


class HtmlContent(StuffContent):
    inner_html: str
    css_class: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some html ({len(self.inner_html)} chars)"

    @override
    def __str__(self) -> str:
        return self.rendered_html()

    @override
    def rendered_plain(self) -> str:
        return self.inner_html

    @override
    def rendered_html(self) -> str:
        doc, tag, text = Doc().tagtext()
        with tag("div", klass=self.css_class):
            text(self.inner_html)
        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.inner_html

    @override
    def rendered_json(self) -> str:
        return json.dumps({"html": self.inner_html, "css_class": self.css_class})
