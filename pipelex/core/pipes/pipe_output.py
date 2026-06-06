from typing import Any, TypeVar

from mthds.models.pipe_output import PipeOutputAbstract
from pydantic import Field

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
from pipelex.graph.graphspec import GraphSpec
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.reporting.reporting_types import AnyTokensUsage


class PipeOutput(PipeOutputAbstract[WorkingMemory]):
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    working_memory_raw: dict[str, Any] | None = None
    pipeline_run_id: str = Field(default=SpecialPipelineId.UNTITLED)
    graph_spec: GraphSpec | None = None
    graph_assembly_error: str | None = None
    # Token usage assembled from the trace-event stream at the end of the run (mirrors graph_spec):
    # the submitter renders the cost report from this field. None when cost reporting was off; an empty
    # list when on but no inference happened. usage_assembly_error mirrors graph_assembly_error.
    tokens_usages: list[AnyTokensUsage] | None = None
    usage_assembly_error: str | None = None

    def prepare_for_temporal(self, library_crate: LibraryCrate | None = None) -> "PipeOutput":
        """Dehydrate WorkingMemory to raw dict for Temporal transit.

        Returns a copy with working_memory serialized to a plain dict
        (no dynamic class metadata), leaving the original unchanged.
        The receiving side must call hydrate_working_memory() to reconstruct
        the typed WorkingMemory after dynamic classes are registered.

        Symmetric with `PipeJob.prepare_for_temporal()`: when `library_crate`
        is None, dehydration is a no-op — there are no dynamic concept classes
        to round-trip, so the typed WorkingMemory can travel as-is.
        """
        if library_crate is None:
            return self
        if not self.working_memory.root:
            return self
        return self.model_copy(
            update={
                "working_memory_raw": self.working_memory.dump_for_temporal(),
                "working_memory": WorkingMemory(),
            }
        )

    @property
    def main_stuff(self) -> Stuff:
        return self.working_memory.get_main_stuff()

    @property
    def optional_main_stuff(self) -> Stuff | None:
        return self.working_memory.get_optional_main_stuff()

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
