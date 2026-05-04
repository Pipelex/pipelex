"""Unit tests for object_class_schema field on ObjectAssignment and TextThenObjectAssignment."""

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import (
    LLMAssignment,
    LLMAssignmentFactory,
    ObjectAssignment,
    TextThenObjectAssignment,
)
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipeline.job_metadata import JobMetadata


class SampleOutputModel(BaseModel):
    name: str
    value: int


def _make_stub_job_metadata() -> JobMetadata:
    return JobMetadata(
        user_id="test-user",
        pipeline_run_id="test-run",
    )


def _make_stub_llm_assignment() -> LLMAssignment:
    return LLMAssignment(
        job_metadata=_make_stub_job_metadata(),
        llm_setting=LLMSetting(model="test-model", temperature=0.7),
        llm_prompt=LLMPrompt(user_text="test prompt"),
    )


def _make_stub_llm_assignment_factory() -> LLMAssignmentFactory:
    return LLMAssignmentFactory(
        job_metadata=_make_stub_job_metadata(),
        llm_setting=LLMSetting(model="test-model", temperature=0.7),
        llm_prompt_factory=LLMPromptTemplate.make_for_structuring_from_preliminary_text(),
    )


class TestAssignmentModelsSchema:
    def test_make_for_class_captures_schema(self) -> None:
        """ObjectAssignment.make_for_class() captures the JSON schema."""
        assignment = ObjectAssignment.make_for_class(
            object_class=SampleOutputModel,
            llm_assignment=_make_stub_llm_assignment(),
        )
        assert assignment.object_class_name == "SampleOutputModel"
        assert assignment.object_class_schema is not None
        assert assignment.object_class_schema["title"] == "SampleOutputModel"
        assert "name" in assignment.object_class_schema["properties"]
        assert "value" in assignment.object_class_schema["properties"]

    def test_object_assignment_json_roundtrip(self) -> None:
        """ObjectAssignment with schema survives JSON round-trip."""
        assignment = ObjectAssignment.make_for_class(
            object_class=SampleOutputModel,
            llm_assignment=_make_stub_llm_assignment(),
        )
        json_str = assignment.model_dump_json()
        restored = ObjectAssignment.model_validate_json(json_str)
        assert restored.object_class_schema == assignment.object_class_schema
        assert restored.object_class_name == "SampleOutputModel"

    def test_text_then_object_assignment_carries_schema(self) -> None:
        """TextThenObjectAssignment can carry an object_class_schema."""
        schema = SampleOutputModel.model_json_schema()
        assignment = TextThenObjectAssignment(
            object_class_name="SampleOutputModel",
            object_class_schema=schema,
            llm_assignment_for_text=_make_stub_llm_assignment(),
            llm_assignment_factory_to_object=_make_stub_llm_assignment_factory(),
        )
        assert assignment.object_class_schema["title"] == "SampleOutputModel"
