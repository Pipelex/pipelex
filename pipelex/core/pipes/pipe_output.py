from typing import Any, TypeVar

from mthds.protocol.pipe_output import PipeOutputAbstract
from pydantic import Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.mermaid_content import MermaidContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContentType
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.graph.graphspec import GraphSpec
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.system.job_metadata import JobMetadata, SpecialPipelineId


class PipeOutput(PipeOutputAbstract[WorkingMemory]):
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    working_memory_raw: dict[str, Any] | None = None
    pipeline_run_id: str = Field(default=SpecialPipelineId.UNTITLED)
    graph_spec: GraphSpec | None = None
    graph_assembly_error: str | None = None
    # Token usage assembled from the trace-event stream at the end of the run (mirrors graph_spec):
    # the submitter renders the cost report from this field. None when cost reporting was off or the run
    # emitted no trace events at all; an empty list when on with events present but no inference happened.
    # usage_assembly_error mirrors graph_assembly_error.
    tokens_usages: list[AnyTokensUsage] | None = None
    usage_assembly_error: str | None = None

    # The job this output was produced under, when there was one.
    #
    # Carried so a transport that offloads an oversized result to storage can key
    # it inside the run's own namespace instead of at the root of a bucket. The
    # Temporal payload codec resolves a payload's scope by attribute, and every
    # payload a run sends IN carries a `job_metadata` to resolve through — the
    # results did not, so the two largest payloads an ordinary run produces (this
    # one and `TracingAssembly`, both ~350 KB) landed outside every prefix the
    # host's erasure cascade deletes and survived deletion of their own run.
    #
    # `run_metadata` is the half that matters here: it is constant for the whole
    # run and holds `storage_scope`. Nothing in the runtime reads this field —
    # it exists to be read by the transport layer that stores the bytes, and the
    # wire DTO (`serialize_completed_output`) names its fields explicitly, so
    # this does not reach an API consumer.
    #
    # Optional: dry runs, signature stubs and tests build outputs with no job in
    # hand. Set once at the run boundary rather than at every `PipeOutput(...)`
    # site — only the top-level output crosses a transport boundary; a sub-pipe's
    # output stays in-process.
    job_metadata: JobMetadata | None = None

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
    def main_stuff_as_yes_no(self) -> YesNoContent:
        """Get main stuff content as YesNoContent if applicable."""
        return self.working_memory.main_stuff_as_yes_no

    @property
    def main_stuff_as_date(self) -> DateContent:
        """Get main stuff content as DateContent if applicable."""
        return self.working_memory.main_stuff_as_date

    @property
    def main_stuff_as_html(self) -> HtmlContent:
        """Get main stuff content as HtmlContent if applicable."""
        return self.working_memory.main_stuff_as_html

    @property
    def main_stuff_as_mermaid(self) -> MermaidContent:
        """Get main stuff content as MermaidContent if applicable."""
        return self.working_memory.main_stuff_as_mermaid


PipeOutputType = TypeVar("PipeOutputType", bound=PipeOutput)
