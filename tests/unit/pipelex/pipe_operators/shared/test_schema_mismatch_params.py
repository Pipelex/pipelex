"""A model's answer that does not fit the step's concept names the model and the concept, whichever operator asked.

The registry's sentence for `model.output_schema_mismatch` reads both parameters, and neither the worker nor the
renderer knows the concept the answer had to fit: the operator that ran the generation does, and fills it, with the
model when no error along the chain names one. Every test here builds the problem in the caller's view under the
unit suite's sweep, which fails a test whose problem lacks a parameter its code requires.
"""

from collections.abc import Callable

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, JudgmentAnswerMismatchError, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.judgment.judgment_models import YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_native_concept
from pipelex.kernel.llm_ops import concrete_llm_model_handle, resolve_llm_setting_for_text
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge, PipeJudgeQuestion
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.shared.schema_mismatch_params import filling_schema_mismatch_params
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.providers.google.google_exceptions import GoogleLLMWorkerError
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory

# The model the worker attributed the failure to, at its chokepoint.
WORKER_MODEL = "worker-model"

_DETAIL = "The model '{model}' gave an answer that does not fit the concept '{concept}', after the runtime asked again."


class _Answer(BaseModel):
    title: str


def _validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        _Answer.model_validate({})
    return exc_info.value


def _rendered_schema_mismatch() -> LLMCompletionError:
    """An answer instructor could not fit to the schema, rendered and attributed as an LLM worker leaves it."""
    metadata = ProviderErrorMetadata(
        provider=ProviderName.OPENAI,
        sdk_exception_type="ValidationError",
        message="1 validation error for Answer: title: Field required",
        status_code=None,
    )
    classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)
    rendered = render_inference_error(
        metadata=metadata,
        classification=classification,
        family=InferenceErrorFamily.LLM,
        model_desc=WORKER_MODEL,
        model_handle=WORKER_MODEL,
    )
    assert isinstance(rendered, LLMCompletionError)
    rendered.fill_model_and_provider(WORKER_MODEL, backend_name="openai")
    return rendered


def _gemini_type_mismatch() -> GoogleLLMWorkerError:
    error = GoogleLLMWorkerError("Google Gemini API returned an object that is not of type Answer: a dict")
    error.fill_model_and_provider(WORKER_MODEL, backend_name="google")
    return error


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run"))


def _assert_names_model_and_concept(*, failure: PipelexError, model: str, concept: str) -> None:
    caller = failure.to_problem(view=ProblemView.CALLER)
    assert caller.code == CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH
    assert caller.params is not None
    params = caller.params.as_wire()
    assert params["model"] == model
    assert params["concept"] == concept
    assert caller.detail == _DETAIL.format(model=model, concept=concept)


def _make_pipe_llm(*, output: str) -> PipeLLM:
    blueprint = PipeLLMBlueprint(description="Write the parcel's summary", output=output, prompt="Summarize the parcel.")
    return PipeFactory[PipeLLM].make_from_blueprint(domain_code="schema_mismatch", pipe_code="summarize_parcel", blueprint=blueprint)


async def _failure_of_pipe_llm(*, pipe_llm: PipeLLM, pipe_run_params: PipeRunParams | None = None) -> PipelexError:
    with pytest.raises(PipelexError) as exc_info:
        await pipe_llm._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            job_metadata=_job_metadata(),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=pipe_run_params or PipeRunParamsFactory.make_run_params(),
        )
    return exc_info.value


class TestPipeLLMSchemaMismatch:
    @pytest.mark.asyncio
    async def test_the_object_path_names_the_concept(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """The worker's rendered failure names its model, and the step gives the concept its output declares."""
        load_empty_library()
        object_call = mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_object", side_effect=_rendered_schema_mismatch())

        failure = await _failure_of_pipe_llm(pipe_llm=_make_pipe_llm(output="native.Number"))

        object_call.assert_awaited_once()
        assert isinstance(failure, PipeRunError)
        _assert_names_model_and_concept(failure=failure, model=WORKER_MODEL, concept="native.Number")

    @pytest.mark.asyncio
    async def test_the_text_path_names_the_concept_and_the_resolved_model(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """Pydantic's refusal carries no model: the step gives the one it resolved, with the concept."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_text", side_effect=_validation_error())

        failure = await _failure_of_pipe_llm(pipe_llm=_make_pipe_llm(output="native.Text"))

        resolved_model = concrete_llm_model_handle(resolve_llm_setting_for_text().model)
        _assert_names_model_and_concept(failure=failure, model=resolved_model, concept="native.Text")

    @pytest.mark.asyncio
    async def test_gemini_s_type_check_passing_the_step_unwrapped_names_the_concept(
        self, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_object", side_effect=_gemini_type_mismatch())

        failure = await _failure_of_pipe_llm(pipe_llm=_make_pipe_llm(output="native.Number"))

        assert isinstance(failure, GoogleLLMWorkerError)
        _assert_names_model_and_concept(failure=failure, model=WORKER_MODEL, concept="native.Number")

    @pytest.mark.asyncio
    async def test_a_dynamic_output_names_the_concept_of_the_run(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """The pipe declares `Dynamic`; the answer had to fit the concept this run resolved it to."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_text", side_effect=_rendered_schema_mismatch())
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_object", side_effect=_rendered_schema_mismatch())

        failure = await _failure_of_pipe_llm(
            pipe_llm=_make_pipe_llm(output="native.Dynamic"),
            pipe_run_params=PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number"),
        )

        _assert_names_model_and_concept(failure=failure, model=WORKER_MODEL, concept="native.Number")


class TestPipeStructureSchemaMismatch:
    @pytest.mark.asyncio
    async def test_the_structured_answer_names_the_concept(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.structure.pipe_structure.generate_object_content", side_effect=_rendered_schema_mismatch())
        blueprint = PipeStructureBlueprint(description="Read the parcel's weight", inputs={"draft_text": "native.Text"}, output="native.Number")
        pipe_structure = PipeFactory[PipeStructure].make_from_blueprint(domain_code="schema_mismatch", pipe_code="read_weight", blueprint=blueprint)
        source = StuffFactory.make_stuff(
            get_native_concept(native_concept=NativeConceptCode.TEXT), content=TextContent(text="The parcel weighs 7 kg."), name="draft_text"
        )

        with pytest.raises(PipeRunError) as exc_info:
            await pipe_structure._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
                job_metadata=_job_metadata(),
                working_memory=WorkingMemoryFactory.make_from_single_stuff(source),
                pipe_run_params=PipeRunParamsFactory.make_run_params(),
            )

        _assert_names_model_and_concept(failure=exc_info.value, model=WORKER_MODEL, concept="native.Number")


class TestPipeJudgeSchemaMismatch:
    @pytest.mark.asyncio
    async def test_the_judge_s_mismatched_answer_names_the_concept(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """The judgment worker's refusal of its own answer passes the step unwrapped; the step gives the verdict's concept."""
        load_empty_library()
        mismatch = JudgmentAnswerMismatchError("The judgment answered a question nobody asked")
        mismatch.fill_model_and_provider(WORKER_MODEL, backend_name="typesafe")
        mocker.patch("pipelex.pipe_operators.judge.pipe_judge.resolve_judgment_setting", return_value=JudgmentSetting(model="judge-deck-model"))
        mocker.patch("pipelex.pipe_operators.judge.pipe_judge.run_judgment", side_effect=mismatch)
        pipe_judge = PipeJudge(
            code="judge_urgency",
            domain_code="schema_mismatch",
            description="Judge whether the parcel is urgent",
            output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.YES_NO)),
            judgment_choice=None,
            prompt_content=UserPromptContent(template=TemplateBlueprint(template="The parcel is due today.", category=TemplateCategory.LLM_PROMPT)),
            question=PipeJudgeQuestion(judgment_question=YesNoQuestion(instructions="Is it urgent?")),
        )

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await pipe_judge._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
                job_metadata=_job_metadata(),
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(),
            )

        _assert_names_model_and_concept(failure=exc_info.value, model=WORKER_MODEL, concept="native.YesNo")


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
        wrapper.__cause__ = _rendered_schema_mismatch()

        _raised_through_filler(error=wrapper)

        assert wrapper.given_params == {"concept": "parcels.Parcel"}
        _assert_names_model_and_concept(failure=wrapper, model=WORKER_MODEL, concept="parcels.Parcel")

    def test_a_chain_naming_no_model_takes_the_step_s(self) -> None:
        carrier = PipeRunError(message="The answer does not fit", run_mode=PipeRunParamsFactory.make_run_params().run_mode, pipe_code="read_line")
        carrier.with_error_code(CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH)

        _raised_through_filler(error=carrier, model_handle="step-model")

        _assert_names_model_and_concept(failure=carrier, model="step-model", concept="parcels.Parcel")
