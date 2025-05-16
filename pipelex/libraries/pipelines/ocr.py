from typing import List, Optional

from pipelex.core.stuff_content import ImageContent, StructuredContent, TextContent


class PageContent(StructuredContent):
    text: Optional[TextContent] = None
    images: List[ImageContent]
    screenshot: Optional[ImageContent] = None
