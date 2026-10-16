from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from kajson.kajson_manager import KajsonManager
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind
from pydantic import model_validator

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.config import get_config
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import PipelexProblem, ProblemView
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_model_deck
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipeline.test_data import LocatedRunFailureTestData, RunFaultViewsTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from typing_extensions import Self


class RunFaultViewsValidatedReview(StructuredContent):
    """Stands in for a structure class a deployment loads from its own library, whose validator writes its own text."""

    idea: TextContent
    overview: TextContent

    @model_validator(mode="after")
    def refuse_by_deployment_rule(self) -> Self:
        msg = RunFaultViewsTestData.DEPLOYMENT_VALIDATOR_TEXT
        raise ValueError(msg)


def _views(error: PipelineExecutionError) -> tuple[PipelexProblem, PipelexProblem]:
    """The run failure's problem as a caller reads it, then as the operator does."""
    return error.to_problem(view=ProblemView.CALLER), error.to_problem(view=ProblemView.OPERATOR)


async def _run_failing(
    *,
    pipe_code: str,
    mthds_content: str,
    inputs: dict[str, Any],
    pipe_run_mode: PipeRunMode = PipeRunMode.LIVE,
) -> PipelineExecutionError:
    if pipe_run_mode.is_dry:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, mock_inputs=True)
        runner = PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode, execution_config=execution_config)
    else:
        runner = PipelexMTHDSProtocol()
    with pytest.raises(PipelineExecutionError) as exc_info:
        await runner.execute(pipe_code=pipe_code, mthds_contents=[mthds_content], inputs=inputs)
    return exc_info.value


@pytest.mark.asyncio(loop_scope="class")
class TestRunFaultViews:
    async def test_parallel_combine_mismatch_is_the_methods_fault(self) -> None:
        """A branch declared `Idea[]` feeding a single field: the method's fault, located at `analyze`, with its remedy."""
        error = await _run_failing(
            pipe_code="flow",
            mthds_content=LocatedRunFailureTestData.PARALLEL_MTHDS,
            inputs={},
            pipe_run_mode=PipeRunMode.DRY,
        )

        caller, operator = _views(error)
        assert caller.code == CoreCode.PIPE_OUTPUT_MULTIPLICITY
        assert caller.domain == ProblemDomain.METHOD
        assert error_code_spec(CoreCode.PIPE_OUTPUT_MULTIPLICITY).status == 422
        assert caller.detail == "Pipe 'analyze' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'."
        assert caller.next_step.kind == StepKind.CHANGE_METHOD
        assert caller.next_step.detail == "Declare the output 'ideas' as 'list', or make pipe 'analyze' produce 'single'."
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "analyze", "path": ["flow", "analyze"]}
        assert caller.diagnostics is None
        # The operator reads the combine's own restatement, with the remedy naming the branch to change.
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "StuffFactoryError"
        assert operator.diagnostics.message.startswith("PipeParallel 'analyze' cannot combine its branch results into its output 'Report'.")
        assert "make branch 'gen_ideas' output a single 'Idea'" in operator.diagnostics.message

    async def test_parallel_combine_refusal_no_multiplicity_explains_is_the_methods_fault(self) -> None:
        """A single `Idea` branch feeding a list of plain texts: no multiplicity to change, the combine's refusal of the field."""
        error = await _run_failing(
            pipe_code="flow",
            mthds_content=RunFaultViewsTestData.PARALLEL_NO_MULTIPLICITY_MTHDS,
            inputs={},
            pipe_run_mode=PipeRunMode.DRY,
        )

        caller, operator = _views(error)
        assert caller.code == CoreCode.PIPE_OUTPUT_INVALID
        assert caller.domain == ProblemDomain.METHOD
        assert caller.detail == "Pipe 'analyze' produced an output that does not fit the concept 'Review', at the fields ideas."
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "analyze", "output_concept": "Review", "fields": ["ideas"]}
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "analyze", "path": ["flow", "analyze"]}
        assert operator.diagnostics is not None
        assert operator.diagnostics.message.startswith("Error combining stuffs for concept Review")

    async def test_a_deployment_validators_text_is_the_operators_alone(self) -> None:
        """A deployment's structure class refusing the combine: its validator's text reaches the operator, never the caller."""
        # The process-global registry, which the run's own library is seeded from, as a deployment's Python module would.
        registry = KajsonManager.get_class_registry()
        registry.register_class(RunFaultViewsValidatedReview)
        try:
            error = await _run_failing(
                pipe_code="flow",
                mthds_content=RunFaultViewsTestData.DEPLOYMENT_VALIDATOR_MTHDS,
                inputs={"topic": "cats"},
            )
        finally:
            registry.unregister_class(RunFaultViewsValidatedReview)

        caller, operator = _views(error)
        validator_text = RunFaultViewsTestData.DEPLOYMENT_VALIDATOR_TEXT
        assert validator_text not in str(caller.to_wire())
        assert "DR-7" not in str(caller.to_wire())
        # The caller still reads which pipe, which concept and which fields, in the code's own sentences.
        assert caller.code == CoreCode.PIPE_OUTPUT_INVALID
        assert caller.detail == (
            "Pipe 'analyze' produced an output that does not fit the concept 'RunFaultViewsValidatedReview', at the fields idea, overview."
        )
        assert caller.next_step.kind == StepKind.CHANGE_METHOD
        assert caller.location is not None
        assert caller.location.pipe == "analyze"
        assert operator.diagnostics is not None
        assert validator_text in operator.diagnostics.message

    async def test_missing_required_input_is_the_callers_fault(self) -> None:
        """A run missing a required input: the input domain, a sentence and a next step naming the input."""
        error = await _run_failing(pipe_code="greet_flow", mthds_content=RunFaultViewsTestData.MISSING_INPUT_MTHDS, inputs={})

        caller, operator = _views(error)
        assert caller.code == CoreCode.INPUT_MISSING
        assert caller.domain == ProblemDomain.INPUT
        assert error_code_spec(CoreCode.INPUT_MISSING).status == 422
        assert caller.detail == "The request does not give the input 'name', which the method requires."
        assert caller.next_step.kind == StepKind.CHANGE_INPUT
        assert caller.next_step.detail == "Add the input 'name' to the request, then send it again."
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "greet_flow", "path": ["greet_flow"]}
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "PipeRunInputsError"

    async def test_model_only_the_method_names_is_the_methods_fault(self) -> None:
        """A step naming, in an inline setting, a model no entry of the deck names: the method's fault, naming the model."""
        error = await _run_failing(
            pipe_code="two_steps",
            mthds_content=LocatedRunFailureTestData.MODEL_MTHDS,
            inputs={"topic": "cats"},
        )

        caller, _ = _views(error)
        unserved_handle = LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE
        assert caller.code == CoreCode.MODEL_UNKNOWN
        assert caller.domain == ProblemDomain.METHOD
        assert caller.detail == f"The method names the llm model '{unserved_handle}', which no catalog knows."
        assert caller.next_step.kind == StepKind.CHANGE_MODEL
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "summarize", "path": ["two_steps", "summarize"]}
        # Provider and model attribution are diagnostics, which no caller reads, whoever's fault it is.
        assert caller.diagnostics is None

    @pytest.mark.parametrize(
        ("_topic", "model_reference"),
        [
            ("preset", f"${RunFaultViewsTestData.DECK_PRESET}"),
            ("alias", f"@{RunFaultViewsTestData.DECK_ALIAS}"),
        ],
    )
    async def test_model_the_deck_names_but_does_not_serve_is_the_operators(self, mocker: MockerFixture, _topic: str, model_reference: str) -> None:
        """A model a preset or an alias of the deck names, which the deployment does not serve, is the operator's to fix."""
        model_deck = get_model_deck()
        unserved_handle = RunFaultViewsTestData.DECK_NAMED_UNSERVED_HANDLE
        mocker.patch.dict(model_deck.llm_presets, {RunFaultViewsTestData.DECK_PRESET: LLMSetting(model=unserved_handle, temperature=0.2)})
        mocker.patch.dict(model_deck.llm_aliases, {RunFaultViewsTestData.DECK_ALIAS: unserved_handle})
        mthds_content = RunFaultViewsTestData.DECK_NAMED_MODEL_MTHDS.replace(RunFaultViewsTestData.MODEL_REFERENCE_SLOT, model_reference)

        error = await _run_failing(pipe_code="summarize_flow", mthds_content=mthds_content, inputs={"topic": "cats"})

        assert error.pipe_code == "summarize"
        caller, operator = _views(error)
        assert caller.code == CoreCode.MODEL_UNAVAILABLE
        assert caller.domain == ProblemDomain.OPERATOR
        assert error_code_spec(CoreCode.MODEL_UNAVAILABLE).status == 501
        # The caller is told what it can do: choose another model, or ask the operator to serve this one.
        assert caller.next_step.kind == StepKind.CHANGE_MODEL
        assert operator.next_step.kind == StepKind.FIX_CONFIGURATION
        assert operator.diagnostics is not None
        assert operator.diagnostics.message == f"Model handle '{unserved_handle}' was not found in the model deck."
        assert caller.diagnostics is None

    async def test_model_output_that_does_not_fit_its_structure_is_no_caller_text(self, mocker: MockerFixture) -> None:
        """A model output the structure refuses, after the re-asks: its text, which quotes the model, stays the operator's."""
        unfit_output_error = LLMCompletionError(
            "Structured generation via 'instructor' failed trying to generate schema: Verdict with error: 1 validation error",
            error_category=InferenceErrorCategory.UNKNOWN,
        )
        fake_content_generator = mocker.MagicMock()
        fake_content_generator.make_object = mocker.AsyncMock(side_effect=unfit_output_error)
        mocker.patch("pipelex.kernel.llm_ops.get_content_generator", return_value=fake_content_generator)

        error = await _run_failing(
            pipe_code="judge_flow",
            mthds_content=RunFaultViewsTestData.STRUCTURED_OUTPUT_MTHDS,
            inputs={"claim": "The sky is green."},
        )

        assert error.pipe_code == "judge"
        caller, operator = _views(error)
        assert "instructor" not in str(caller.to_wire())
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "judge", "path": ["judge_flow", "judge"]}
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "LLMCompletionError"
