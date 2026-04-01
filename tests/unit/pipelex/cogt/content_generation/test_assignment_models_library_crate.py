"""Unit tests for LibraryCrate field on ObjectAssignment and TextThenObjectAssignment."""

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
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipeline.job_metadata import JobMetadata


class SampleOutputModel(BaseModel):
    name: str
    value: int


def _make_minimal_crate() -> LibraryCrate:
    return LibraryCrate(
        concepts={},
        pipes={},
        domains={},
        source_map={},
        fingerprint="abc123",
    )


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


class TestAssignmentModelsLibraryCrate:
    def test_object_assignment_default_library_crate_is_none(self) -> None:
        """ObjectAssignment defaults to library_crate=None for backward compat."""
        assignment = ObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_object=_make_stub_llm_assignment(),
        )
        assert assignment.library_crate is None

    def test_object_assignment_with_library_crate(self) -> None:
        """ObjectAssignment can carry a LibraryCrate."""
        crate = _make_minimal_crate()
        assignment = ObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_object=_make_stub_llm_assignment(),
            library_crate=crate,
        )
        assert assignment.library_crate is not None
        assert assignment.library_crate.fingerprint == "abc123"

    def test_object_assignment_round_trip_with_crate(self) -> None:
        """ObjectAssignment with library_crate survives JSON round-trip."""
        crate = _make_minimal_crate()
        assignment = ObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_object=_make_stub_llm_assignment(),
            library_crate=crate,
        )
        json_str = assignment.model_dump_json()
        restored = ObjectAssignment.model_validate_json(json_str)
        assert restored.library_crate is not None
        assert restored.library_crate.fingerprint == crate.fingerprint

    def test_object_assignment_round_trip_without_crate(self) -> None:
        """ObjectAssignment without library_crate survives JSON round-trip."""
        assignment = ObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_object=_make_stub_llm_assignment(),
        )
        json_str = assignment.model_dump_json()
        restored = ObjectAssignment.model_validate_json(json_str)
        assert restored.library_crate is None

    def test_make_for_class_forwards_library_crate(self) -> None:
        """ObjectAssignment.make_for_class() forwards library_crate."""
        crate = _make_minimal_crate()
        assignment = ObjectAssignment.make_for_class(
            object_class=SampleOutputModel,
            llm_assignment=_make_stub_llm_assignment(),
            library_crate=crate,
        )
        assert assignment.library_crate is crate

    def test_make_for_class_default_library_crate_is_none(self) -> None:
        """ObjectAssignment.make_for_class() defaults library_crate to None."""
        assignment = ObjectAssignment.make_for_class(
            object_class=SampleOutputModel,
            llm_assignment=_make_stub_llm_assignment(),
        )
        assert assignment.library_crate is None

    def test_text_then_object_assignment_default_library_crate_is_none(self) -> None:
        """TextThenObjectAssignment defaults to library_crate=None."""
        assignment = TextThenObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_text=_make_stub_llm_assignment(),
            llm_assignment_factory_to_object=_make_stub_llm_assignment_factory(),
        )
        assert assignment.library_crate is None

    def test_text_then_object_assignment_with_library_crate(self) -> None:
        """TextThenObjectAssignment can carry a LibraryCrate."""
        crate = _make_minimal_crate()
        assignment = TextThenObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_text=_make_stub_llm_assignment(),
            llm_assignment_factory_to_object=_make_stub_llm_assignment_factory(),
            library_crate=crate,
        )
        assert assignment.library_crate is not None
        assert assignment.library_crate.fingerprint == "abc123"

    def test_text_then_object_assignment_crate_accessible(self) -> None:
        """TextThenObjectAssignment's library_crate is accessible after construction."""
        crate = _make_minimal_crate()
        assignment = TextThenObjectAssignment(
            object_class_name="SampleOutputModel",
            llm_assignment_for_text=_make_stub_llm_assignment(),
            llm_assignment_factory_to_object=_make_stub_llm_assignment_factory(),
            library_crate=crate,
        )
        assert assignment.library_crate is not None
        assert assignment.library_crate is crate
        assert assignment.library_crate.fingerprint == "abc123"
