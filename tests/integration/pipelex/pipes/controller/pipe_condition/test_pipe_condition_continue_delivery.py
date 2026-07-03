"""PipeCondition's `continue` outcome delivers the current main stuff by passing it through.

A pipe run always delivers a main stuff. For `continue`, the delivered main stuff is the one
already in the working memory (pass-through). When there is nothing to pass through (e.g. the
condition is the entry pipe and memory holds only named inputs), the run must fail loudly at the
pipe level with an actionable error — not crash downstream (graph tracer, delivery, telemetry)
with a bare WorkingMemoryStuffNotFoundError.
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


def _make_continue_only_condition() -> PipeCondition:
    """A condition whose every outcome is `continue` (a pure pass-through gate)."""
    blueprint = PipeConditionBlueprint(
        description="Pass-through gate for continue-delivery tests",
        inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
        output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
        expression_template="{% if input_text.text %}skip{% else %}skip{% endif %}",
        outcomes={"skip": SpecialOutcome.CONTINUE},
        default_outcome=SpecialOutcome.CONTINUE,
    )
    return PipeFactory[PipeCondition].make_from_blueprint(
        domain_code="test_integration",
        pipe_code="continue_gate",
        blueprint=blueprint,
    )


def _make_input_text_stuff():
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text="hello"),
        name="input_text",
    )


def _make_run_params(run_mode: PipeRunMode) -> PipeRunParams:
    # Constructed directly (not via the factory) so a keyless boot's forced-DRY coercion cannot
    # silently swap which controller code path (live vs dry) the test exercises.
    return PipeRunParams(run_mode=run_mode, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionContinueDelivery:
    async def test_continue_with_main_stuff_passes_it_through(self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]):
        """With a main stuff in memory, `continue` delivers it unchanged."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        input_text_stuff = _make_input_text_stuff()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_run_params(PipeRunMode.LIVE),
        )

        assert pipe_output.main_stuff.stuff_code == input_text_stuff.stuff_code
        # Run identity must survive the pass-through: the continue path builds its own PipeOutput,
        # so it must stamp pipeline_run_id like every other controller — otherwise the blocking
        # bridge serializes SpecialPipelineId.UNTITLED and callers track the wrong run.
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id

    async def test_continue_without_main_stuff_fails_loud(self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]):
        """With nothing to pass through, `continue` is a clear PipeRunError at the pipe level."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.set_stuff(name="input_text", stuff=_make_input_text_stuff())

        with pytest.raises(PipeRunError) as exc_info:
            await pipe_condition.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=_make_run_params(PipeRunMode.LIVE),
            )
        assert "continue_gate" in str(exc_info.value)
        assert "main stuff" in str(exc_info.value)

    async def test_dry_run_of_special_outcomes_only_condition_without_main_stuff_fails_loud(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """Dry-run parity: an all-special-outcomes condition with no pre-existing main stuff cannot deliver."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.set_stuff(name="input_text", stuff=_make_input_text_stuff())

        with pytest.raises(PipeRunError):
            await pipe_condition.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=_make_run_params(PipeRunMode.DRY),
            )

    async def test_dry_run_continue_with_main_stuff_preserves_run_id(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """Dry-run parity path (all-special-outcomes condition with a pre-existing main stuff) must also
        stamp pipeline_run_id, like the live continue path — the dry-run PipeOutput is built directly too.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(_make_input_text_stuff())

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_run_params(PipeRunMode.DRY),
        )

        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id
