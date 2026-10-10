"""A field that never holds nothing refuses an explicit null, so a binding reading it never records an absence.

The standard's rule says a field that is `required` or carries a `default_value` never holds nothing, and a
binding step derives its static presence from that rule alone: a sequence ending with a binding of such a
field validates with a non-optional output. The runtime class used to admit `None` on a defaulted field
(`X | None = default`) and on a required `native.Anything` field (`Any`), so an input nulling either one was
kept, and the binding recorded a declared absence its own derivation had ruled out. The class now refuses
that `None` where the input enters the run, and leaving the key out binds the default.
"""

from typing import Any

import pytest

from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.exceptions import InputShapingError
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.interpreter_hub import clear_current_library, get_library_manager, get_pipe_router
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.runtime_hub import get_report_delegate

_BINDING_MTHDS = """
domain = "never_nothing"
description = "Bind fields that never hold nothing"

[concept.Inner]
description = "An inner value"

[concept.Inner.structure]
label = { type = "text", description = "a label" }

[concept.Doc]
description = "A document"

[concept.Doc.structure]
note = { type = "text", description = "a note", default_value = "fallback" }
inner = { type = "concept", concept_ref = "Inner", description = "inner", required = true }
payload = { type = "concept", concept_ref = "native.Anything", description = "any value", required = true }

[pipe.bind_note]
type = "PipeSequence"
description = "Bind the defaulted note"
inputs = { doc = "Doc" }
output = "Text"
steps = [{ from = "doc.note", result = "note" }]
"""


def _cleanup(*, pipeline_run_id: str, library_id: str) -> None:
    """Tear down what `pipeline_run_setup` leaves open on its success path, which its caller owns when it runs the job itself."""
    get_report_delegate().clear_event_log(context_key=pipeline_run_id)
    tracer_manager = GraphTracerManager.get_instance()
    if tracer_manager is not None:
        tracer_manager.close_tracer(pipeline_run_id)
    get_library_manager().teardown(library_id=library_id)
    clear_current_library()


async def _run_bind_note(*, doc: dict[str, Any]) -> AbsenceRecord | TextContent:
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
    pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
        storage_scope="test/scope",
        read_scope=None,
        user_id="test-user",
        execution_config=execution_config,
        mthds_contents=[_BINDING_MTHDS],
        pipe_code="bind_note",
        inputs={"doc": doc},
    )
    try:
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)
    finally:
        _cleanup(pipeline_run_id=pipeline_run_id, library_id=library_id)
    resolved = pipe_output.working_memory.resolve_main_stuff()
    if isinstance(resolved, AbsenceRecord):
        return resolved
    return resolved.content_as(content_type=TextContent)


@pytest.mark.asyncio(loop_scope="class")
class TestBindingAFieldThatNeverHoldsNothing:
    async def test_an_omitted_defaulted_field_binds_its_default(self):
        bound = await _run_bind_note(doc={"inner": {}, "payload": {"any": "value"}})

        assert isinstance(bound, TextContent)
        assert bound.text == "fallback"

    async def test_a_set_defaulted_field_binds_its_value(self):
        bound = await _run_bind_note(doc={"note": "written", "inner": {}, "payload": [1, 2]})

        assert isinstance(bound, TextContent)
        assert bound.text == "written"

    @pytest.mark.parametrize(
        ("doc", "nulled_field"),
        [
            ({"note": None, "inner": {}, "payload": 1}, "note"),
            ({"inner": {}, "payload": None}, "payload"),
        ],
    )
    async def test_an_explicit_null_on_a_field_that_never_holds_nothing_is_refused(self, doc: dict[str, Any], nulled_field: str):
        with pytest.raises(InputShapingError) as exc_info:
            await _run_bind_note(doc=doc)

        assert exc_info.value.variable_name == "doc"
        assert nulled_field in str(exc_info.value)
