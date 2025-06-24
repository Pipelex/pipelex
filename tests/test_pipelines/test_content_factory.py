from pipelex.core.stuff_content import StructuredContent


class MockRegisteredContent(StructuredContent):
    title: str
    description: str


class AnotherMockContent(StructuredContent):
    message: str
    priority: int
