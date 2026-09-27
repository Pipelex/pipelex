"""Pin: the refusals a `PipeCondition` raises behind its bundle's load checks are the caller's faults too.

A bundle's load refuses an outcome naming no pipe, an expression that does not parse and a chosen pipe's
undeclared input before any condition runs, so a run of a loaded bundle does not reach these raise sites:
the tests call the condition's run arms directly. Each refusal is classified as the caller's fault, keeps
its message under STRICT disclosure with a next step, and quotes no text of the condition, which may be a
host library's.
"""

from pathlib import Path
from typing import Any, Callable

import pytest

from pipelex.base_exceptions import DisclosureMode
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_run.located_failure import find_root_fault
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

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


def _strict_problem_document(error: PipeRunError) -> dict[str, Any]:
    return error.to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)


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

        document = _strict_problem_document(exc_info.value)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["detail"] == (
            "PipeCondition 'length_gate' chose pipe 'test_integration2.capitalize_long_text', whose required inputs are missing: input_text."
        )
        assert document["user_action"] == {
            "kind": "change_input",
            "detail": (
                "Provide the missing required inputs of 'test_integration2.capitalize_long_text', which PipeCondition 'length_gate' chose: "
                "input_text."
            ),
        }

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
        document = _strict_problem_document(exc_info.value)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert (
            document["detail"] == "Dry run failed for pipe 'parse_gate' (PipeCondition): its expression does not parse at line 2 of that expression."
        )
        assert "frobnicate_the_parcel" not in document["detail"]
        assert "input_text" not in document["detail"]
        assert document["user_action"] == {
            "kind": "change_input",
            "detail": "Fix the expression of PipeCondition 'parse_gate' so that it parses as a Jinja2 expression.",
        }

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

        document = _strict_problem_document(exc_info.value)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["detail"] == (
            "Dry run failed for PipeCondition 'route_gate': its outcomes name pipes that do not exist: "
            "test_integration.send_by_barge, test_integration.send_rush."
        )
        assert "rush_lane" not in document["detail"]
        assert document["user_action"] == {
            "kind": "change_input",
            "detail": (
                "Declare the pipes test_integration.send_by_barge, test_integration.send_rush, "
                "or change the outcomes of PipeCondition 'route_gate' to name existing pipes."
            ),
        }
