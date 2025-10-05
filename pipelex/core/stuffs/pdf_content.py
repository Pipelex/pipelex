from typing_extensions import override
from yattag import Doc

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.path_utils import interpret_path_or_url


class PDFContent(StuffContent):
    url: str

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
        return f"{url_desc} of a PDF document"

    @override
    def rendered_plain(self) -> str:
        return self.url

    @override
    def rendered_html(self) -> str:
        doc = Doc()
        doc.stag("a", href=self.url, klass="msg-pdf")
        doc.text(self.url)

        return doc.getvalue()

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"[{self.url}]({self.url})"
