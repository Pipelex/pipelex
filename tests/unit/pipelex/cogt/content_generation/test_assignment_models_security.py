"""Wire-format perimeter tests: prove that x-python-* schema extensions survive
serialization through ObjectAssignment, so the codegen boundary in
SchemaToModelFactory is the only line of defense (and works).
"""

from typing import Any

import pytest

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


def _make_stub_job_metadata() -> JobMetadata:
    return JobMetadata(
        user_id="test-user",
        pipeline_run_id="test-run",
    )


def _make_stub_llm_assignment() -> LLMAssignment:
    return LLMAssignment(
        job_metadata=_make_stub_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        llm_setting=LLMSetting(model="test-model", temperature=0.7),
        llm_prompt=LLMPrompt(user_text="test prompt"),
    )


def _malicious_schema() -> dict[str, Any]:
    return {
        "title": "Innocent",
        "type": "object",
        "properties": {"hit": {"$ref": "#/$defs/Run"}},
        "$defs": {"Run": {"x-python-import": {"module": "subprocess", "name": "run"}}},
    }


class TestAssignmentModelsSecurity:
    def test_object_assignment_preserves_x_python_import_through_json_roundtrip(self) -> None:
        """A malicious x-python-import in object_class_schema survives the wire format unchanged.

        The dict[str, Any] field is intentionally permissive — rejection happens at the
        codegen boundary (SchemaToModelFactory), not at deserialization.
        """
        assignment = ObjectAssignment(
            object_class_name="Innocent",
            object_class_schema=_malicious_schema(),
            llm_assignment_for_object=_make_stub_llm_assignment(),
        )
        json_str = assignment.model_dump_json()
        restored = ObjectAssignment.model_validate_json(json_str)
        assert restored.object_class_schema == _malicious_schema()
        assert restored.object_class_schema["$defs"]["Run"]["x-python-import"] == {
            "module": "subprocess",
            "name": "run",
        }

    def test_codegen_rejects_post_roundtrip_unsafe_schema(self) -> None:
        """Closes the loop: a payload that survives the wire crossing is rejected at codegen.

        This is the actual contract: the wire format is permissive on purpose, the
        boundary in SchemaToModelFactory.make_from_json_schema is the chokepoint.
        """
        assignment = ObjectAssignment(
            object_class_name="Innocent",
            object_class_schema=_malicious_schema(),
            llm_assignment_for_object=_make_stub_llm_assignment(),
        )
        restored = ObjectAssignment.model_validate_json(assignment.model_dump_json())
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(restored.object_class_schema, class_name=restored.object_class_name)
        assert "x-python-import" in str(exc_info.value)
