from typing import TypeVar

from pydantic import BaseModel, Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.mermaid_content import MermaidContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContentType
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.pipeline_models import SpecialPipelineId


class PipeOutput(BaseModel):
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    pipeline_run_id: str = Field(default=SpecialPipelineId.UNTITLED)

    @property
    def main_stuff(self) -> Stuff:
        return self.working_memory.get_main_stuff()

    def main_stuff_as_list(self, item_type: type[StuffContentType]) -> ListContent[StuffContentType]:
        """Get main stuff content as ListContent with items of type StuffContentType.
        If the items are of possibly various types, use item_type=StuffContent.
        """
        return self.working_memory.main_stuff_as_list(item_type=item_type)

    def main_stuff_as_items(self, item_type: type[StuffContentType]) -> list[StuffContentType]:
        """Get main stuff content as ListContent with items of type StuffContentType.
        Return the actual items
        """
        return self.working_memory.main_stuff_as_list(item_type=item_type).items

    def main_stuff_as(self, content_type: type[StuffContentType]) -> StuffContentType:
        """Get main stuff content as StuffContentType.
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
