from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.config import get_config
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_model_deck
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipeline.test_data import LocatedRunFailureTestData, StrictMethodFaultsTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _strict_problem_document(error: PipelineExecutionError) -> dict[str, Any]:
    """The body a hosted runner answers with: the run failure's report, projected under STRICT disclosure."""
    return error.to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)


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
class TestStrictMethodFaults:
    async def test_parallel_combine_mismatch_is_the_callers_fault(self) -> None:
        """A branch declared `Idea[]` feeding a single field: HTTP 422, the input domain, and the combine's reason at `analyze`."""
        error = await _run_failing(
            pipe_code="flow",
            mthds_content=LocatedRunFailureTestData.PARALLEL_MTHDS,
            inputs={},
            pipe_run_mode=PipeRunMode.DRY,
        )

        document = _strict_problem_document(error)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["error_type"] == "StuffFactoryError"
        assert document["detail"] != INTERNAL_ERROR_PLACEHOLDER
        assert document["detail"].startswith("Pipe 'analyze' failed (flow → analyze): Error combining stuffs for concept Report")
        assert "'ideas': expected located_failure_parallel__Idea, got ListContent" in document["detail"]
        assert document["user_action"]["kind"] == "change_input"
        assert "PipeParallel 'analyze'" in document["user_action"]["detail"]
        assert "located_failure_parallel.Report" in document["user_action"]["detail"]

    async def test_missing_required_input_is_the_callers_fault(self) -> None:
        """A run missing a required input: HTTP 422, with a message and a next step naming the input."""
        error = await _run_failing(pipe_code="greet_flow", mthds_content=StrictMethodFaultsTestData.MISSING_INPUT_MTHDS, inputs={})

        document = _strict_problem_document(error)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["error_type"] == "PipeRunInputsError"
        assert document["detail"] == "Pipe 'greet_flow' failed: Live run of PipeSequence 'greet_flow': missing required inputs: name."
        assert document["user_action"] == {"kind": "change_input", "detail": "Provide the missing required inputs of 'greet_flow': name."}

    async def test_model_only_the_method_names_is_the_callers_fault(self) -> None:
        """A step naming, in an inline setting, a model no entry of the deck names: HTTP 422, and its reason."""
        error = await _run_failing(
            pipe_code="two_steps",
            mthds_content=LocatedRunFailureTestData.MODEL_MTHDS,
            inputs={"topic": "cats"},
        )

        document = _strict_problem_document(error)
        unserved_handle = LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["error_type"] == "ModelNotFoundError"
        assert (
            document["detail"]
            == f"Pipe 'summarize' failed (two_steps → summarize): Model handle '{unserved_handle}' was not found in the model deck."
        )
        # Provider and model attribution never reach a STRICT caller, whoever's fault it is.
        assert "model" not in document

    @pytest.mark.parametrize(
        ("_topic", "model_reference"),
        [
            ("preset", f"${StrictMethodFaultsTestData.DECK_PRESET}"),
            ("alias", f"@{StrictMethodFaultsTestData.DECK_ALIAS}"),
        ],
    )
    async def test_model_the_deck_names_but_does_not_serve_stays_redacted(self, mocker: MockerFixture, _topic: str, model_reference: str) -> None:
        """A model a preset or an alias of the deck names, which the deployment does not serve, is not the caller's fault."""
        model_deck = get_model_deck()
        unserved_handle = StrictMethodFaultsTestData.DECK_NAMED_UNSERVED_HANDLE
        mocker.patch.dict(model_deck.llm_presets, {StrictMethodFaultsTestData.DECK_PRESET: LLMSetting(model=unserved_handle, temperature=0.2)})
        mocker.patch.dict(model_deck.llm_aliases, {StrictMethodFaultsTestData.DECK_ALIAS: unserved_handle})
        mthds_content = StrictMethodFaultsTestData.DECK_NAMED_MODEL_MTHDS.replace(StrictMethodFaultsTestData.MODEL_REFERENCE_SLOT, model_reference)

        error = await _run_failing(pipe_code="summarize_flow", mthds_content=mthds_content, inputs={"topic": "cats"})

        assert error.pipe_code == "summarize"
        report = error.to_error_report()
        assert (
            report.message
            == f"Pipe 'summarize' failed (summarize_flow → summarize): Model handle '{unserved_handle}' was not found in the model deck."
        )
        document = _strict_problem_document(error)
        assert document["status"] == 500
        assert document["error_domain"] == "config"
        assert document["error_type"] == "ModelNotFoundError"
        assert document["detail"] == INTERNAL_ERROR_PLACEHOLDER

    async def test_model_output_that_does_not_fit_its_structure_stays_redacted(self, mocker: MockerFixture) -> None:
        """A model output the structure refuses, after the re-asks, is data-dependent: not flagged caller-facing."""
        unfit_output_error = LLMCompletionError(
            "Structured generation via 'instructor' failed trying to generate schema: Verdict with error: 1 validation error",
            error_category=InferenceErrorCategory.UNKNOWN,
        )
        fake_content_generator = mocker.MagicMock()
        fake_content_generator.make_object = mocker.AsyncMock(side_effect=unfit_output_error)
        mocker.patch("pipelex.kernel.llm_ops.get_content_generator", return_value=fake_content_generator)

        error = await _run_failing(
            pipe_code="judge_flow",
            mthds_content=StrictMethodFaultsTestData.STRUCTURED_OUTPUT_MTHDS,
            inputs={"claim": "The sky is green."},
        )

        assert error.pipe_code == "judge"
        report = error.to_error_report()
        assert report.error_type == "LLMCompletionError"
        assert report.caller_facing_message is False
        document = _strict_problem_document(error)
        assert document["status"] == 500
        assert document["error_domain"] == "runtime"
        assert document["detail"] == INTERNAL_ERROR_PLACEHOLDER
