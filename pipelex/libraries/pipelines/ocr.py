from typing import List, Optional

from pipelex.core.stuff_content import ImageContent, StructuredContent, TextAndImageContent


class PageContent(StructuredContent):
    text_and_image_content: TextAndImageContent
    screenshot: Optional[ImageContent] = None
