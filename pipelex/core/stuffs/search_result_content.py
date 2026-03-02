import html as html_module

from pydantic import Field
from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class SearchSourceContent(StuffContent):
    """Represents a single search source with name, URL, and optional snippet."""

    name: str
    url: str
    snippet: str | None = None

    @property
    @override
    def short_desc(self) -> str:
        return f"source: {self.name}"

    @override
    def rendered_plain(self) -> str:
        result = f"- {self.name}: {self.url}"
        if self.snippet:
            result += f"\n  {self.snippet}"
        return result

    @override
    def rendered_html(self) -> str:
        name_escaped = html_module.escape(self.name)
        url_escaped = html_module.escape(self.url)
        result = f'<li><a href="{url_escaped}">{name_escaped}</a>'
        if self.snippet:
            snippet_escaped = html_module.escape(self.snippet)
            result += f"<br/><small>{snippet_escaped}</small>"
        result += "</li>"
        return result

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        result = f"- [{self.name}]({self.url})"
        if self.snippet:
            result += f"\n  {self.snippet}"
        return result

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        source_text = Text()
        source_text.append(self.name, style="bold")
        source_text.append(f" ({self.url})", style="dim cyan")
        if self.snippet:
            source_text.append(f"\n  {self.snippet}", style="dim italic")
        return source_text


class SearchResultContent(StuffContent):
    """Represents the result of a search query with an answer and list of sources."""

    answer: str
    sources: list[SearchSourceContent] = Field(default_factory=empty_list_factory_of(SearchSourceContent))

    @property
    @override
    def short_desc(self) -> str:
        nb_sources = len(self.sources)
        return f"search result ({len(self.answer)} chars, {nb_sources} source{'s' if nb_sources != 1 else ''})"

    @override
    def rendered_plain(self) -> str:
        result = self.answer
        if self.sources:
            result += "\n\nSources:\n"
            result += "\n".join(source.rendered_plain() for source in self.sources)
        return result

    @override
    def rendered_html(self) -> str:
        answer_escaped = html_module.escape(self.answer)
        result = f"<div><p>{answer_escaped}</p>"
        if self.sources:
            source_items = "".join(source.rendered_html() for source in self.sources)
            result += f"<h4>Sources</h4><ul>{source_items}</ul>"
        result += "</div>"
        return result

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        result = self.answer
        if self.sources:
            result += "\n\n**Sources:**\n\n"
            result += "\n".join(source.rendered_markdown(level=level, is_pretty=is_pretty) for source in self.sources)
        return result

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        group = Group()

        # Title
        title_text = Text("Search Result:", style="bold cyan")
        group.renderables.append(title_text)

        # Answer as markdown
        group.renderables.append(Markdown(self.answer))

        # Sources
        if self.sources:
            group.renderables.append(Text())  # spacing
            sources_header = Text(f"Sources ({len(self.sources)}):", style="bold yellow")
            group.renderables.append(sources_header)

            for index, source in enumerate(self.sources):
                if index > 0:
                    group.renderables.append(Text())  # spacing between sources
                source_renderable = source.rendered_pretty(depth=depth + 1)
                group.renderables.append(source_renderable)

        return group
