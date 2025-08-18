from pipelex.core.stuff.stuff_content import StructuredContent


class Article(StructuredContent):
    """Test model for article data."""

    title: str
    description: str
    date: str
