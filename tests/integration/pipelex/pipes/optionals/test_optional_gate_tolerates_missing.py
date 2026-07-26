"""The `@?` fix, observable at the runtime miss-gates: a variable that a pipe's templates
reference but whose input is declared optional (`?`) must NOT be presence-required by the
SubPipe / PipeCondition gates. With neither a value nor an absence record for the slot, the
pipe still runs and its guarded template takes the absent arm (matching the pipe's own
`validate_before_run` trichotomy, which already tolerates a missing optional).
"""

from typing import Callable

import pytest

from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata

_DOMAIN_CODE = "test_optionals_gate"


def _make_live_run_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


def _register_guarded_compose() -> None:
    """A PipeCompose whose template references the optional `maybe_note` (guarded), so its
    `required_variables()` include the optional name — exactly what trips a naive gate.
    """
    compose = PipeFactory[PipeCompose].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="gate_compose_sink",
        blueprint=PipeComposeBlueprint(
            description="Guarded compose over an optional slot",
            inputs={"topic": "Text", "maybe_note": "Text?"},
            output="Text",
            template="report about {{ topic }}{% if maybe_note %} (note: {{ maybe_note }}){% endif %}",
        ),
    )
    get_pipe_library().add_new_pipe(pipe=compose)


@pytest.mark.asyncio(loop_scope="class")
class TestOptionalGateToleratesMissing:
    async def test_sub_pipe_gate_tolerates_missing_optional(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """`maybe_note` has neither a value nor a record: the SubPipe gate must not hard-fail;
        the compose runs on the absent arm.
        """
        load_empty_library()
        _register_guarded_compose()
        sequence = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="gate_sequence",
            blueprint=PipeSequenceBlueprint(
                description="Single guarded step",
                inputs={"topic": "Text", "maybe_note": "Text?"},
                output="Text",
                steps=[SubPipeBlueprint(pipe="gate_compose_sink", result="final_report")],
            ),
        )
        get_pipe_library().add_new_pipe(pipe=sequence)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(StuffFactory.make_from_str("penalties", name="topic"))

        pipe_output = await sequence.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )
        assert pipe_output.main_stuff.as_text.text == "report about penalties"

    async def test_condition_gate_tolerates_missing_optional(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """The PipeCondition chosen-pipe gate applies the same rule for the chosen pipe's
        declared-optional inputs.
        """
        load_empty_library()
        _register_guarded_compose()
        condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="gate_condition",
            blueprint=PipeConditionBlueprint(
                description="Routes to the guarded compose",
                inputs={"topic": "Text", "maybe_note": "Text?"},
                output="Text",
                expression="'go'",
                outcomes={"go": "gate_compose_sink"},
                default_outcome="fail",
            ),
        )
        get_pipe_library().add_new_pipe(pipe=condition)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(StuffFactory.make_from_str("penalties", name="topic"))

        pipe_output = await condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )
        assert pipe_output.main_stuff.as_text.text == "report about penalties"
