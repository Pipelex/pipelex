"""End-to-end pin of the entry concept scope: input shaping prefers the entry pipe's own domain.

This is the wiring test, not the rule test — the rule rows live in
tests/unit/pipelex/libraries/test_concept_library_entry_lookup.py. Here a real run through
``PipelexMTHDSProtocol.execute`` loads TWO bundles whose domains both declare ``Memo``, and the
caller's input envelope names the bare code. Without the scope threading
(pipeline_run_setup → prepare_pipe_job → shape_inputs → StuffFactory →
get_required_entry_concept), the bare code is ambiguous and the run fails; with it, the entry
pipe's own domain wins deterministically.
"""

import pytest

from pipelex.config import get_config
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

_ALPHA_MTHDS = """
domain = "ecs_alpha"
description = "Entry domain declaring its own Memo"

[concept.Memo]
description = "An alpha memo"
refines = "Text"

[pipe.write_memo]
type = "PipeLLM"
description = "Rewrite a memo"
inputs = { memo = "Memo" }
output = "Text"
prompt = "Rewrite $memo"
"""

_BETA_MTHDS = """
domain = "ecs_beta"
description = "Sibling domain declaring a same-named Memo"

[concept.Memo]
description = "A beta memo"
refines = "Text"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestEntryConceptScope:
    async def test_bare_envelope_concept_resolves_to_the_entry_pipe_domain(self) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
            mock_inputs=False,
        )
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)

        response = await runner.execute(
            pipe_code="write_memo",
            mthds_contents=[_ALPHA_MTHDS, _BETA_MTHDS],
            inputs={"memo": {"concept": "Memo", "content": "quarterly numbers"}},
        )

        shaped_memo = response.pipe_output.working_memory.get_stuff("memo")
        assert shaped_memo.concept.concept_ref == "ecs_alpha.Memo"
