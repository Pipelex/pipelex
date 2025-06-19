from pipelex.core.stuff_content import ListContent, StructuredContent, TextContent


class RandomListContent(ListContent[TextContent]):
    pass


class Article(StructuredContent):
    title: str
    description: str
    date: str
