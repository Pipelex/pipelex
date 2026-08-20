from typing import Any, TypeVar

from mthds.protocol.pipe_output import PipeOutputAbstract
from pydantic import Field, PrivateAttr

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
    # it inside the run's own namespace instead of at the root of a bucket. Every
    # payload a run sends IN carries a `job_metadata` for a transport to resolve a
    # scope through; the results did not, so the two largest payloads an ordinary
    # run produces landed outside every prefix a host's erasure cascade deletes
    # and survived deletion of their own run.
    #
    # **A private attribute behind a property, NOT a model field, and that is the
    # whole point.** `PipeOutput` is on the wire: `pipelex-api` returns it inside
    # `PipelexApiExecuteResponse` and publishes its schema in a committed OpenAPI
    # artifact. As a field, this would put `user_id`, `request_id`, `otel_context`
    # and `trace_context` into a public API's response body and its documented
    # schema — which `test_openapi_contract.py` exists to prevent, and which it
    # caught. As a private attribute it is readable by a transport resolving a
    # scope (attribute access on the live object, before serialization) and absent
    # from `model_dump`, from `model_json_schema`, and therefore from the wire.
    #
    # It does not survive serialization, and does not need to: a transport reads it
    # on the object it is about to serialize, in the process that produced it.
    _job_metadata: JobMetadata | None = PrivateAttr(default=None)

    @property
    def job_metadata(self) -> JobMetadata | None:
        return self._job_metadata

    def set_job_metadata(self, *, job_metadata: JobMetadata | None) -> None:
        """Set the job_metadata a transport reads to place this result's bytes.

        A METHOD, not a `@job_metadata.setter`: this repo's keyword-only convention
        rewrites a positional setter parameter into a keyword-only one, which is not
        a valid property-setter signature. A named method takes the keyword happily
        and says what it does at the call site.
        """
        self._job_metadata = job_metadata

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
