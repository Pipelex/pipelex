"""PipeCondition's `continue` outcome resolves the declared output as ABSENT (design §14, breaking).

Phase-1 semantics: `continue` records a declared-absent AbsenceRecord for the declared output and
returns success — memory otherwise unchanged (a previous main stuff stays under its own name but no
longer masquerades as this pipe's output). The old pass-through-or-error behavior is gone; the
ergonomic replacement for pass-through is coalescing (phase 2).
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


def _make_continue_only_condition() -> PipeCondition:
    """A condition whose every outcome is `continue` (a pure absence gate)."""
    blueprint = PipeConditionBlueprint(
        description="Absence gate for continue-delivery tests",
        inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
        output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}?",
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
    async def test_continue_records_declared_absent_output(self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]):
        """`continue` succeeds and resolves the declared output as a declared-absent record."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.set_stuff(name="input_text", stuff=_make_input_text_stuff())

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_run_params(PipeRunMode.LIVE),
            output_name="gate_result",
        )

        result_memory = pipe_output.working_memory
        resolved_main = result_memory.resolve_main_stuff()
        assert isinstance(resolved_main, AbsenceRecord)
        assert resolved_main.kind == AbsenceKind.DECLARED_ABSENT
        assert resolved_main.producing_pipe == "continue_gate"
        # The record names the declared output slot and carries the evaluated expression.
        assert resolved_main.variable_name == "gate_result"
        assert "skip" in resolved_main.reason
        assert result_memory.get_optional_absence("gate_result") == resolved_main
        # Memory otherwise unchanged: the input is still there, untainted.
        assert result_memory.get_optional_stuff("input_text") is not None
        # Run identity must survive the absence path: the continue arm builds its own PipeOutput,
        # so it must stamp pipeline_run_id like every other controller — otherwise the blocking
        # bridge serializes SpecialPipelineId.UNTITLED and callers track the wrong run.
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id

    async def test_continue_supersedes_previous_main_stuff(self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]):
        """A previous main stuff no longer passes through: it stays under its own name while the
        condition's output resolves absent (the migration idiom — consume it explicitly downstream).
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        input_text_stuff = _make_input_text_stuff()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)
        assert working_memory.get_optional_main_stuff() is not None

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_run_params(PipeRunMode.LIVE),
        )

        result_memory = pipe_output.working_memory
        resolved_main = result_memory.resolve_main_stuff()
        assert isinstance(resolved_main, AbsenceRecord)
        assert resolved_main.kind == AbsenceKind.DECLARED_ABSENT
        # The previous value remains addressable under its own name.
        previous = result_memory.get_optional_stuff("input_text")
        assert previous is not None
        assert previous.stuff_code == input_text_stuff.stuff_code
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id

    async def test_dry_run_all_special_outcomes_records_absence(self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]):
        """Dry-run parity: an all-special-outcomes condition records the declared output absent
        instead of raising — same semantics as the live continue arm, run id stamped alike.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.set_stuff(name="input_text", stuff=_make_input_text_stuff())

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_run_params(PipeRunMode.DRY),
        )

        resolved_main = pipe_output.working_memory.resolve_main_stuff()
        assert isinstance(resolved_main, AbsenceRecord)
        assert resolved_main.kind == AbsenceKind.DECLARED_ABSENT
        assert resolved_main.producing_pipe == "continue_gate"
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id

    async def test_dry_run_all_special_outcomes_supersedes_previous_main_stuff(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """Dry-run parity with the live supersede rule: a pre-existing main stuff stays under its
        own name while the condition's output resolves absent.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition = _make_continue_only_condition()
        input_text_stuff = _make_input_text_stuff()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_run_params(PipeRunMode.DRY),
        )

        result_memory = pipe_output.working_memory
        assert isinstance(result_memory.resolve_main_stuff(), AbsenceRecord)
        assert result_memory.get_optional_stuff("input_text") is not None
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id
