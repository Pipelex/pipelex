"""The filler of `model.output_schema_mismatch`'s parameters, alone: what it gives, and what it leaves as it found it.

`PipeLLM`, `PipeStructure` and `PipeJudge` wrap their generation with it; each one's own test drives a failure through
the step.
"""

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.pipe_operators.shared.schema_mismatch_params import filling_schema_mismatch_params
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from tests.helpers.schema_mismatch import WORKER_MODEL, assert_names_model_and_concept, make_rendered_schema_mismatch


def _raised_through_filler(*, error: PipelexError, model_handle: str = "step-model") -> PipelexError:
    with pytest.raises(PipelexError) as exc_info, filling_schema_mismatch_params(concept_ref="parcels.Parcel", model_handle=model_handle):
        raise error
    assert exc_info.value is error
    return exc_info.value


class TestFillingSchemaMismatchParams:
    def test_an_error_of_another_code_is_left_untouched(self) -> None:
        error = LLMCompletionError("The provider failed", error_category=InferenceErrorCategory.AMBIGUOUS).with_error_code(CoreCode.PROVIDER_FAILED)

        _raised_through_filler(error=error)

        assert error.given_params == {}

    def test_a_concept_the_carrier_gave_is_kept(self) -> None:
        carrier = PipeRunError(message="The answer does not fit", run_mode=PipeRunParamsFactory.make_run_params().run_mode, pipe_code="read_line")
        carrier.with_error_code(CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH).with_params(concept="parcels.Given", model="carrier-model")

        _raised_through_filler(error=carrier)

        assert carrier.given_params == {"concept": "parcels.Given", "model": "carrier-model"}

    def test_the_model_the_chain_names_wins_over_the_step_s(self) -> None:
        wrapper = PipeRunError(message="The step failed", run_mode=PipeRunParamsFactory.make_run_params().run_mode, pipe_code="read_line")
        wrapper.__cause__ = make_rendered_schema_mismatch()

        _raised_through_filler(error=wrapper)

        assert wrapper.given_params == {"concept": "parcels.Parcel"}
        assert_names_model_and_concept(failure=wrapper, model=WORKER_MODEL, concept="parcels.Parcel")

    def test_a_chain_naming_no_model_takes_the_step_s(self) -> None:
        carrier = PipeRunError(message="The answer does not fit", run_mode=PipeRunParamsFactory.make_run_params().run_mode, pipe_code="read_line")
        carrier.with_error_code(CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH)

        _raised_through_filler(error=carrier, model_handle="step-model")

        assert_names_model_and_concept(failure=carrier, model="step-model", concept="parcels.Parcel")
