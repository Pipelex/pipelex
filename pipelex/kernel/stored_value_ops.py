"""Load the stored values a step must read synchronously, through the content generator's leaf.

A text past the inline threshold travels as a reference (`pipelex.core.stuffs.stored_value_content`). Where a value is
read by a leaf, the leaf loads it: a prompt renders in its content-generation leaf for that reason. A few readers run in
the step itself, which on a host runtime is workflow code that reads no storage: a `PipeCondition` expression is the one
today. Such a reader finds the stored values it reads with this op, which hands their URLs to the content generator's
`load_stored_texts` leaf and keeps the texts it returns on the contents, so they render synchronously afterwards.

Nothing is dispatched when every value read is inline or already loaded, which is the common case: a condition nearly
always tests a short value. When something is loaded, the texts enter the workflow's history on a host runtime, which
is acceptable for the rare value it is.
"""

from collections.abc import Mapping
from typing import Any

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.runtime_hub import get_content_generator
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.uri.uri_read_scope import UriReference


async def load_stored_values_through_leaf(*, roots: Mapping[str, Any], job_metadata: JobMetadata, cogt_run_params: CogtRunParams) -> int:
    """Load every stored value under the given roots through the content generator's leaf, and keep each on its content.

    The contents' fields are left unchanged, so a dump of each is still its reference.

    Args:
        roots: The values the reader reads, each keyed by its name: a stuff's content keyed by the stuff's name.
        job_metadata: The step's metadata, whose run's read scope the leaf authorizes each read against.
        cogt_run_params: The run's execution mode.

    Returns:
        The number of values loaded, 0 when nothing was dispatched.

    Raises:
        UriReadRefusedError: A stored value's URL is outside the run's read scope.
        StoredValueUnreadableError: A stored text is not a value of its content's kind.
    """
    with job_metadata.log_context():
        stored_values = find_unloaded_stored_values(roots=roots)
        uri_references = [
            UriReference(uri=stored_value.content.url, position=stored_value.position)
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
            stored_value.content.accept_loaded_text(text=loaded_text)
        return len(loaded_texts)
