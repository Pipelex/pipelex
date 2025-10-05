from pipelex.core.stuffs.structured_content import StructuredContent


class Article(StructuredContent):
    """Test model for article data."""

    title: str
    description: str
    date: str
