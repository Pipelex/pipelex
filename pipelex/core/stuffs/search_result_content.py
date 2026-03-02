from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class SearchSourceContent(StructuredContent):
    """Represents a single search source with name, URL, and optional snippet."""

    name: str
    url: str
    snippet: str | None = None


class SearchResultContent(StructuredContent):
    """Represents the result of a search query with an answer and list of sources."""

    answer: str
    sources: list[SearchSourceContent] = Field(default_factory=empty_list_factory_of(SearchSourceContent))
