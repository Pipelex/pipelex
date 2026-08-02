"""What a kernel extract call hands back.

The produced pages plus the one intermediate the caller cannot recompute without redoing the deck
chain: the resolved `ExtractSetting`, whose `model` is what the interpreter's execution-graph tracer
records. The memory contract holds as everywhere else in the kernel — **the returned `memory` is the
result**, and no caller may rely on the argument having been mutated.

The serialization note on `pipelex.kernel.llm_results` applies here too, for the same reason: `pages`
holds concrete `PageContent` instances, so use `kajson` rather than a plain `model_dump()` if one of
these ever crosses a boundary. Nothing serializes them today.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent


class ExtractResult(BaseModel):
    """The outcome of a kernel extract call."""

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: ListContent[PageContent]
    extract_setting: ExtractSetting
