from pipelex.core.stuffs.structured_content import StructuredContent


class Article(StructuredContent):
    """Test model for article data."""

    title: str
    location: str
    description: str
    year: int
