from typing import List, Type, TypeVar

from pydantic import BaseModel, Field

from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import (
    HtmlContent,
    ImageContent,
    ListContent,
    MermaidContent,
    NumberContent,
    StuffContentType,
    TextAndImagesContent,
    TextContent,
)
from pipelex.core.working_memory import WorkingMemory


class PipeOutput(BaseModel):
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)

    @property
    def main_stuff(self) -> Stuff:
        return self.working_memory.get_main_stuff()

    def main_stuff_as_list(self, item_type: Type[StuffContentType]) -> ListContent[StuffContentType]:
        """
        Get main stuff content as ListContent with items of type StuffContentType.
        If the items are of possibly various types, use item_type=StuffContent.
        """
        return self.working_memory.main_stuff_as_list(item_type=item_type)

    def main_stuff_as_items(self, item_type: Type[StuffContentType]) -> List[StuffContentType]:
        """
        Get main stuff content as ListContent with items of type StuffContentType.
        Return the actual items
        """
        return self.working_memory.main_stuff_as_list(item_type=item_type).items

    def main_stuff_as(self, content_type: Type[StuffContentType]) -> StuffContentType:
        """
        Get main stuff content as StuffContentType.
        If the items are of possibly various types, use item_type=StuffContent.
        """
        return self.working_memory.main_stuff_as(content_type=content_type)

    @property
    def main_stuff_as_text(self) -> TextContent:
        """Get main stuff content as TextContent if applicable."""
        return self.working_memory.main_stuff_as_text

    @property
    def main_stuff_as_str(self) -> str:
        """Get main stuff content as TextContent if applicable and return the text."""
        return self.working_memory.main_stuff_as_text.text

    @property
    def main_stuff_as_image(self) -> ImageContent:
        """Get main stuff content as ImageContent if applicable."""
        return self.working_memory.main_stuff_as_image

    @property
    def main_stuff_as_text_and_image(self) -> TextAndImagesContent:
        """Get main stuff content as TextAndImageContent if applicable."""
        return self.working_memory.main_stuff_as_text_and_image

    @property
    def main_stuff_as_number(self) -> NumberContent:
        """Get main stuff content as NumberContent if applicable."""
        return self.working_memory.main_stuff_as_number

    @property
    def main_stuff_as_html(self) -> HtmlContent:
        """Get main stuff content as HtmlContent if applicable."""
        return self.working_memory.main_stuff_as_html

    @property
    def main_stuff_as_mermaid(self) -> MermaidContent:
        """Get main stuff content as MermaidContent if applicable."""
        return self.working_memory.main_stuff_as_mermaid


PipeOutputType = TypeVar("PipeOutputType", bound=PipeOutput)
