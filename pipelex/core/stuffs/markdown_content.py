from typing import TYPE_CHECKING

from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.markdown.markdown_parser import render_markdown_as_html
from pipelex.tools.misc.pretty import require_rich_for_rendering

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable


# The content class of the native `Markdown` concept, which refines `Text`: a text written in Markdown, which
# the views and the renditions format rather than show as it is. It keeps `TextContent`'s single `text` field,
# holding the Markdown source, so a Markdown value goes wherever a text goes, and a prompt, the plain view and
# the saved `.md` file get the source as it is. The views that format are the HTML one, which converts it with
# the shared parser (`render_markdown_as_html`), and the pretty one, which Rich renders as Markdown.
#
# Inside an HTML template, a Markdown value prints as its converted HTML with no filter: the class follows
# markupsafe's `__html__` convention, which HTML autoescaping reads, and `StuffArtefact` answers it for a stuff
# whose content defines it. The conversion is safe to insert: the parser escapes raw HTML, and markdown-it
# refuses `javascript:` and similar link targets.
#
# The docstring is the concept's description, as for every native content class: pydantic publishes it as the
# schema's description, which an LLM reads when it writes a list of Markdown texts.
class MarkdownContent(TextContent):
    """A text written in Markdown"""

    text: str = Field(description="The text, written in Markdown")

    @property
    @override
    def short_desc(self) -> str:
        return f"some markdown ({len(self.text)} chars)"

    @override
    def rendered_html(self) -> str:
        return render_markdown_as_html(self.text)

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        # Always Markdown: `TextContent` sniffs for HTML first, but raw HTML in a Markdown source is text.
        require_rich_for_rendering()
        from rich.markdown import Markdown

        return Markdown(self.text)

    def __html__(self) -> str:
        """The HTML that markupsafe inserts as it is: the converted Markdown, which holds no raw HTML from the source."""
        return self.rendered_html()
