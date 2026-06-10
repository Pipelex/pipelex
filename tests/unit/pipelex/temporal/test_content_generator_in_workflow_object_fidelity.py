"""Unit tests for the ``--mock-inference`` object-mock fidelity guard on the Temporal arm (review F2).

The activity (``act_llm_gen_object*``) builds the mock from the schema-reconstructed class, then
``ContentGeneratorInWorkflow.make_object`` re-validates it against the original class. When the original
class enforces an invariant the JSON-schema round-trip cannot capture (here a custom ``@field_validator``),
that re-validation fails — and must surface as a clear typed ``MockInferenceObjectFidelityError`` rather than
an opaque ``pydantic.ValidationError`` mid-workflow. The guard is armed by either leaf-mock trigger
(``is_mock_inference`` or ``run_mode=DRY`` — eng review D6): a LIVE provider's invalid output keeps its
existing ``ValidationError``. ``execute_activity`` is mocked to return the synthetic object, so no Temporal
server (or real provider) is involved.
"""

import pytest
from pydantic import BaseModel, ValidationError, field_validator
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.exceptions import MockInferenceObjectFidelityError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow


class ConstrainedName(BaseModel):
    """Original output class with an invariant the JSON-schema round-trip cannot capture."""

    name: str

    @field_validator("name")
    @classmethod
    def _require_prefix(cls, value: str) -> str:
        if not value.startswith("PFX_"):
            msg = "name must start with 'PFX_'"
            raise ValueError(msg)
        return value


class RawName(BaseModel):
    """Stand-in for what the (mocked) activity returns: a permissive reconstructed-class instance."""

    name: str


def _make_generator() -> ContentGeneratorInWorkflow:
    return ContentGeneratorInWorkflow()


def _job_metadata() -> JobMetadata:
    return JobMetadata(user_id="u", pipeline_run_id="run", pipe_code="my_pipe")


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("patch_workflow_runtime")
class TestContentGeneratorInWorkflowObjectFidelity:
    @pytest.fixture
    def patch_workflow_runtime(self, mocker: MockerFixture) -> None:
        mocker.patch("temporalio.workflow.unsafe.is_replaying_history_events", return_value=False)

    async def test_make_object_raises_typed_error_on_fidelity_gap(self, mocker: MockerFixture) -> None:
        """A mock-inference object whose re-validation fails surfaces MockInferenceObjectFidelityError."""
        mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock, return_value=RawName(name="bad"))

        with pytest.raises(MockInferenceObjectFidelityError) as exc_info:
            await _make_generator().make_object(
                job_metadata=_job_metadata(),
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE, is_mock_inference=True),
                object_class=ConstrainedName,
                llm_setting_for_object=LLMSetting(model="test-llm", temperature=0.5),
                llm_prompt_for_object=LLMPrompt(user_text="hello"),
            )
        assert ConstrainedName.__name__ in str(exc_info.value)

    async def test_make_object_list_raises_typed_error_on_fidelity_gap(self, mocker: MockerFixture) -> None:
        """The list path applies the same per-item guard."""
        mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock, return_value=[RawName(name="bad")])

        with pytest.raises(MockInferenceObjectFidelityError):
            await _make_generator().make_object_list(
                job_metadata=_job_metadata(),
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE, is_mock_inference=True),
                object_class=ConstrainedName,
                llm_setting_for_object_list=LLMSetting(model="test-llm", temperature=0.5),
                llm_prompt_for_object_list=LLMPrompt(user_text="hello"),
            )

    async def test_dry_run_mode_arm_raises_typed_error(self, mocker: MockerFixture) -> None:
        """run_mode=DRY (without is_mock_inference) also arms the fidelity guard (eng review D6)."""
        mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock, return_value=RawName(name="bad"))

        with pytest.raises(MockInferenceObjectFidelityError):
            await _make_generator().make_object(
                job_metadata=_job_metadata(),
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
                object_class=ConstrainedName,
                llm_setting_for_object=LLMSetting(model="test-llm", temperature=0.5),
                llm_prompt_for_object=LLMPrompt(user_text="hello"),
            )

    async def test_non_mock_run_keeps_raw_validation_error(self, mocker: MockerFixture) -> None:
        """Outside --mock-inference the guard is inert: a re-validation failure stays a raw ValidationError."""
        mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock, return_value=RawName(name="bad"))

        with pytest.raises(ValidationError):
            await _make_generator().make_object(
                job_metadata=_job_metadata(),
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
                object_class=ConstrainedName,
                llm_setting_for_object=LLMSetting(model="test-llm", temperature=0.5),
                llm_prompt_for_object=LLMPrompt(user_text="hello"),
            )
