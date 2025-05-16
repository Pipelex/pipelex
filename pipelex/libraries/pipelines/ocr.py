from typing import List, Optional

from pipelex.core.stuff_content import ImageContent, StructuredContent, TextContent


class PageContent(StructuredContent):
    text: TextContent
    images: List[ImageContent]
    screenshot: Optional[ImageContent] = None
