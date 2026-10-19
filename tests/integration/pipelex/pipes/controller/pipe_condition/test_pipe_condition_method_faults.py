"""Pin: the refusals a `PipeCondition` raises behind its bundle's load checks are the caller's faults too.

A bundle's load refuses an outcome naming no pipe, an expression that does not parse and a chosen pipe's
undeclared input before any condition runs, so a run of a loaded bundle does not reach these raise sites:
the tests call the condition's run arms directly. Each refusal is classified as the method's fault, the
caller reads its code's sentence and next step, rendered from the parameters the raise site gives, and
neither quotes text of the condition, which may be a host library's.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, RetryVerdict

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import NodeKind
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_run.located_failure import find_root_fault
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import ConditionResolvedEvent, ExecutionDataEvent
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config

_TEXT = f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
_CONDITION_LIBRARY = Path("tests/integration/pipelex/pipes/controller/pipe_condition")


def _make_condition(*, pipe_code: str, expression_template: str, outcomes: dict[str, str], default_outcome: str) -> PipeCondition:
    blueprint = PipeConditionBlueprint(
        description="A condition whose run arms the test calls directly",
        inputs={"input_text": _TEXT},
        output=_TEXT,
        expression_template=expression_template,
        outcomes=outcomes,
        default_outcome=default_outcome,
    )
    return PipeFactory[PipeCondition].make_from_blueprint(domain_code="test_integration", pipe_code=pipe_code, blueprint=blueprint)


def _caller_problem_document(error: PipeRunError) -> dict[str, Any]:
    """The caller's problem document: a method fault, never retried, with the caller's own message on the operator's side."""
    problem = error.to_problem(view=ProblemView.CALLER)
    assert problem.domain == ProblemDomain.METHOD
    assert problem.retry == RetryVerdict.NO
    assert error_code_spec(CoreCode(problem.code)).status == 422
    operator = error.to_problem(view=ProblemView.OPERATOR)
    assert operator.diagnostics is not None
    assert operator.diagnostics.message == error.message
    return problem.to_wire()


@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionMethodFaults:
    async def test_a_chosen_pipe_missing_its_inputs_is_the_callers_fault(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ) -> None:
        load_test_library([_CONDITION_LIBRARY])
        pipe_condition = _make_condition(
            pipe_code="length_gate",
            expression_template="long",
            outcomes={"long": "test_integration2.capitalize_long_text"},
            default_outcome="test_integration2.add_prefix_short_text",
        )

        with pytest.raises(PipeRunError) as exc_info:
            await pipe_condition._live_run_controller_pipe(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            )

        assert exc_info.value.message == (
            "PipeCondition 'length_gate' chose pipe 'test_integration2.capitalize_long_text', whose required inputs are missing: input_text."
        )
        document = _caller_problem_document(exc_info.value)
        assert document["code"] == CoreCode.PIPE_INPUT_UNRESOLVED
        assert document["detail"] == "Pipe 'length_gate' could not read 'input_text', which an earlier step should have produced."
        assert document["location"] == {"pipe": "length_gate"}
        assert document["next_step"] == {
            "kind": "change_method",
            "detail": "Make an earlier step produce 'input_text' for pipe 'length_gate', then run the method again.",
        }

    @pytest.mark.parametrize(
        ("outcome", "resolution"),
        [
            ("test_integration2.capitalize_long_text", None),
            ("fail", ("long", "long")),
        ],
        ids=["chosen_pipe_missing_its_inputs", "fail_outcome"],
    )
    async def test_the_trace_records_a_choice_only_once_it_is_final(
        self,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
        outcome: str,
        resolution: tuple[str, str] | None,
    ) -> None:
        """A chosen pipe whose inputs are missing fails the condition before it runs: the trace records no outcome taken.

        A `fail` outcome is the condition's own final choice, so its resolution is recorded before the condition raises.
        Neither starts a pipe under the condition, so the graph draws no SELECTED_OUTCOME edge.
        """
        load_test_library([_CONDITION_LIBRARY])
        pipe_condition = _make_condition(
            pipe_code="length_gate",
            expression_template="long",
            outcomes={"long": outcome},
            default_outcome="test_integration2.add_prefix_short_text",
        )
        pipeline_run_id = job_metadata.run_metadata.pipeline_run_id
        event_log = InMemoryEventLog()
        tracer_manager = GraphTracerManager.get_or_create_instance()
        root_context = tracer_manager.open_tracer(
            graph_id=pipeline_run_id,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            pipeline_run_id=pipeline_run_id,
            run_mode=PipeRunMode.LIVE,
        )
        try:
            condition_node_id, condition_context = tracer_manager.on_pipe_start(
                pipe_ref=f"tests.{pipe_condition.code}",
                trace_context=root_context,
                pipe_code=pipe_condition.code,
                pipe_type=pipe_condition.type,
                node_kind=NodeKind.CONTROLLER,
                started_at=datetime.now(UTC),
            )
            assert condition_node_id is not None
            with pytest.raises(PipeRunError):
                await pipe_condition._live_run_controller_pipe(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                    job_metadata=job_metadata.model_copy(update={"trace_context": condition_context}),
                    working_memory=WorkingMemoryFactory.make_empty(),
                    pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
                )
        finally:
            graph_spec = tracer_manager.close_tracer(pipeline_run_id)

        events = event_log.read_events(pipeline_run_id)
        resolutions = [(event.rendered_value, event.selected_outcome) for event in events if isinstance(event, ConditionResolvedEvent)]
        selected_outcomes = [
            event.execution_data["selected_outcome"]
            for event in events
            if isinstance(event, ExecutionDataEvent) and "selected_outcome" in event.execution_data
        ]
        if resolution is None:
            assert resolutions == []
            assert selected_outcomes == []
        else:
            assert resolutions == [resolution]
            assert selected_outcomes == [outcome]
        assert graph_spec is not None
        assert [edge for edge in graph_spec.edges if edge.kind.is_selected_outcome] == []

    async def test_an_expression_that_does_not_parse_names_its_line_only(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ) -> None:
        """The refusal names the line the expression fails at, never a token of it or of the parser's diagnosis."""
        load_test_library([_CONDITION_LIBRARY])
        pipe_condition = _make_condition(
            pipe_code="parse_gate",
            expression_template="{{ input_text.text }}",
            outcomes={"long": "test_integration2.capitalize_long_text"},
            default_outcome="test_integration2.add_prefix_short_text",
        ).model_copy(update={"expression": "{{ input_text.text }}\n{% frobnicate_the_parcel %}"})

        with pytest.raises(PipeRunError) as exc_info:
            await pipe_condition._dry_run_controller_pipe(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            )

        # The refusal is the root fault a run and a dry-run verdict report, not the parser error that quotes the expression.
        assert find_root_fault(error=exc_info.value) is exc_info.value
        assert exc_info.value.message == (
            "Dry run failed for pipe 'parse_gate' (PipeCondition): its expression does not parse at line 2 of that expression."
        )
        document = _caller_problem_document(exc_info.value)
        assert document["code"] == CoreCode.METHOD_TEMPLATE_INVALID
        assert document["detail"] == "The template 'expression' of pipe 'parse_gate' is invalid (does not parse at line 2 of that expression)."
        assert document["location"] == {"pipe": "parse_gate"}
        for text in (str(document), exc_info.value.message):
            assert "frobnicate_the_parcel" not in text
            assert "input_text" not in text

    async def test_outcomes_naming_no_pipe_are_the_callers_fault(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ) -> None:
        """The refusal names the missing pipes, sorted, and no longer prints the outcome map."""
        load_test_library([_CONDITION_LIBRARY])
        pipe_condition = _make_condition(
            pipe_code="route_gate",
            expression_template="{{ input_text.text }}",
            outcomes={"rush_lane": "test_integration.send_rush", "slow_lane": "test_integration.send_by_barge"},
            default_outcome="test_integration.send_by_barge",
        )

        with pytest.raises(PipeRunError) as exc_info:
            await pipe_condition._dry_run_controller_pipe(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            )

        assert exc_info.value.message == (
            "Dry run failed for PipeCondition 'route_gate': its outcomes name pipes that do not exist: "
            "test_integration.send_by_barge, test_integration.send_rush."
        )
        document = _caller_problem_document(exc_info.value)
        assert document["code"] == CoreCode.METHOD_PIPE_UNRESOLVED
        assert document["params"] == {"pipe": "route_gate", "missing": "test_integration.send_by_barge, test_integration.send_rush"}
        assert document["location"] == {"pipe": "route_gate"}
        assert document["next_step"]["kind"] == "change_method"
        for text in (str(document), exc_info.value.message):
            assert "rush_lane" not in text
