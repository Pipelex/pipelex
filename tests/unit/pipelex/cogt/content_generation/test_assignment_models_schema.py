"""Unit tests for object_class_schema field on ObjectAssignment."""

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
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
        cogt_run_params=CogtRunParams(),
        llm_setting=LLMSetting(model="test-model", temperature=0.7),
        llm_prompt=LLMPrompt(user_text="test prompt"),
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
