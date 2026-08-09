"""What a kernel search call hands back.

Two intermediates ride along because the kernel is where they are produced and the interpreter's
execution-graph tracer records them: the rendered query, and the `SearchSetting` *after* handle
resolution and pipe-level overrides — which is not the one the caller passed in, so it has to come
back. The memory contract holds as everywhere else: **the returned `memory` is the result**.

The serialization note on `pipelex.kernel.llm_results` applies here too — `content` is annotated with
the base `StuffContent`, so use `kajson` rather than a plain `model_dump()`.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class SearchResult(BaseModel):
    """The outcome of a kernel search call.

    `content` is a sourced answer, or an instance of the requested structure class when one was asked
    for.
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    rendered_query: str
    search_setting: SearchSetting
