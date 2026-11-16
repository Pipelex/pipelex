"""Load the stored values a step must read synchronously, through the content generator's leaf.

A text past the inline threshold travels as a reference (`pipelex.core.stuffs.stored_value_content`). Where a value is
read by a leaf, the leaf loads it: a PipeLLM or PipeStructure prompt renders in its content-generation leaf for that
reason. The other readers render in the step itself, which on a host runtime is workflow code that reads no storage: a
`PipeCondition` expression, a PipeImgGen prompt and negative prompt, a PipeJudge's evidence and questions, a PipeSearch
query, and a PipeCompose template or a construct's template fields. Such a reader finds the stored values its templates
read with `load_stored_values_read_from_memory`, which hands their URLs to the content generator's `load_stored_texts`
leaf and keeps the texts it returns on the contents, so they render synchronously afterwards.

Nothing is dispatched when every value read is inline or already loaded, which is the common case. When something is
loaded, the texts enter the workflow's history on a host runtime, where the payload codec moves any payload of 256 KiB
or more to storage. The design accepts that cost for these readers, whose rendered output enters the history anyway.
"""

from collections.abc import Collection, Mapping
from typing import Any

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.exceptions import StoredValueUnreadableError
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.runtime_hub import get_content_generator
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.tools.uri.uri_read_scope import UriReference


async def load_stored_values_through_leaf(
    *, roots: Mapping[str, Any], read_paths: Collection[str] | None, job_metadata: JobMetadata, cogt_run_params: CogtRunParams
) -> int:
    """Load the stored values under the given roots that the reader reads, through the content generator's leaf.

    Each loaded text is kept on its content, whose fields are left unchanged, so a dump of it is still its reference.

    Args:
        roots: The values the reader reads, each keyed by its name: a stuff's content keyed by the stuff's name.
        read_paths: The dotted paths the reader reads through, so a stored value it never reads, such as a field beside
            the one it reads, is not loaded (`StoredValueAtPath.is_read_through`). ``None`` loads every stored value.
        job_metadata: The step's metadata, whose run's read scope the leaf authorizes each read against.
        cogt_run_params: The run's execution mode.

    Returns:
        The number of values loaded, 0 when nothing was dispatched.

    Raises:
        UriReadRefusedError: A stored value's URL is outside the run's read scope.
        StoredValueUnreadableError: A stored text is not a value of its content's kind.
    """
    with job_metadata.log_context():
        stored_values = find_unloaded_stored_values(roots=roots, read_paths=read_paths)
        uri_references = [
            UriReference(uri=stored_value.content.url, position=stored_value.position, input_name=stored_value.input_name)
            for stored_value in stored_values
            if stored_value.content.url is not None
        ]
        if not uri_references:
            return 0
        loaded_texts = await get_content_generator().load_stored_texts(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            uri_references=uri_references,
        )
        for stored_value, loaded_text in zip(stored_values, loaded_texts, strict=True):
            try:
                stored_value.content.accept_loaded_text(text=loaded_text)
            except StoredValueUnreadableError as exc:
                # The refusal names the input, as a load in this process names it (`load_stored_value`).
                exc.with_input(input_name=stored_value.input_name)
                raise
        return len(loaded_texts)


async def load_stored_values_read_from_memory(
    *, memory: WorkingMemory, read_paths: Collection[str], job_metadata: JobMetadata, cogt_run_params: CogtRunParams
) -> int:
    """Load, through the content generator's leaf, the stored values of the memory that a reader's templates read.

    The templates render against the memory afterwards, in the step, over the texts kept on the contents. A stored value
    beside what the paths read, such as a sibling field or a stuff no template names, is not loaded, and paths reading
    only inline values dispatch nothing.

    Args:
        memory: The step's working memory, whose stuffs the paths start from, each by its name or an alias of it.
        read_paths: The dotted paths through which the reader's templates read (`detect_jinja2_read_paths`), computed
            once per pipe. A path whose root names no stuff, such as a run parameter or an extra context value, reads
            nothing from the memory.
        job_metadata: The step's metadata, whose run's read scope the leaf authorizes each read against.
        cogt_run_params: The run's execution mode.

    Returns:
        The number of values loaded, 0 when nothing was dispatched.

    Raises:
        UriReadRefusedError: A stored value's URL is outside the run's read scope.
        StoredValueUnreadableError: A stored text is not a value of its content's kind.
    """
    with job_metadata.log_context():
        read_contents: dict[str, Any] = {}
        for read_name in sorted({get_root_from_dotted_path(read_path) for read_path in read_paths}):
            read_stuff = memory.get_optional_stuff(name=read_name)
            if read_stuff is not None:
                read_contents[read_name] = read_stuff.content
        return await load_stored_values_through_leaf(
            roots=read_contents, read_paths=read_paths, job_metadata=job_metadata, cogt_run_params=cogt_run_params
        )
