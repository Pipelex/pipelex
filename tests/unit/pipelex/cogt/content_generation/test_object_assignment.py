"""Tests for ObjectAssignment deserialization and validation.

Verifies that ObjectAssignment can be deserialized (e.g. by Temporal's data converter)
without requiring the referenced class to be in the class registry at deserialization time.
The class registry check happens at execution time via validate_before_execution().
"""

import pytest
from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.exceptions import LLMAssignmentError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.hub import get_class_registry
from pipelex.pipeline.job_metadata import JobMetadata


def _make_llm_assignment() -> LLMAssignment:
    """Create a minimal LLMAssignment for testing."""
    return LLMAssignment(
        job_metadata=JobMetadata(
            user_id="test",
            pipeline_run_id="test-run",
        ),
        llm_setting=LLMSetting(model="test-model", temperature=0.5),
        llm_prompt=LLMPrompt(user_text="test prompt"),
    )


class TestObjectAssignment:
    """Tests for ObjectAssignment init, serialization, and validation."""

    def test_deserialize_with_unregistered_class(self) -> None:
        """ObjectAssignment should be constructable even if the class is not in the registry.

        This is critical for Temporal workers: the workflow input is deserialized before
        the library_crate is loaded and classes are registered.
        """
        assignment = ObjectAssignment(
            object_class_name="some_domain__UnknownClass",
            llm_assignment_for_object=_make_llm_assignment(),
        )
        assert assignment.object_class_name == "some_domain__UnknownClass"

    def test_deserialize_with_registered_class(self) -> None:
        """ObjectAssignment should work normally when the class IS registered."""

        class FakeContent(BaseModel):
            value: str

        registry = get_class_registry()
        registry.register_class(FakeContent, name="FakeContent", should_warn_if_already_registered=False)

        assignment = ObjectAssignment(
            object_class_name="FakeContent",
            llm_assignment_for_object=_make_llm_assignment(),
        )
        assert assignment.object_class_name == "FakeContent"

    def test_roundtrip_serialization_with_unregistered_class(self) -> None:
        """ObjectAssignment should survive a model_dump/model_validate cycle without class registry."""
        assignment = ObjectAssignment(
            object_class_name="missing_domain__MissingClass",
            llm_assignment_for_object=_make_llm_assignment(),
        )
        dumped = assignment.model_dump()
        restored = ObjectAssignment.model_validate(dumped)
        assert restored.object_class_name == "missing_domain__MissingClass"

    def test_validate_before_execution_raises_for_unregistered_class(self) -> None:
        """validate_before_execution should raise when the class is NOT in the registry."""
        assignment = ObjectAssignment(
            object_class_name="nonexistent__MissingClass",
            llm_assignment_for_object=_make_llm_assignment(),
        )
        with pytest.raises(LLMAssignmentError, match="not in the class registry"):
            assignment.validate_before_execution()

    def test_validate_before_execution_passes_for_registered_class(self) -> None:
        """validate_before_execution should succeed when the class IS in the registry."""

        class AnotherFakeContent(BaseModel):
            score: int

        registry = get_class_registry()
        registry.register_class(AnotherFakeContent, name="AnotherFakeContent", should_warn_if_already_registered=False)

        assignment = ObjectAssignment(
            object_class_name="AnotherFakeContent",
            llm_assignment_for_object=_make_llm_assignment(),
        )
        assignment.validate_before_execution()
