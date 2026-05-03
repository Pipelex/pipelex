"""Integration tests at the llm_gen_object / llm_gen_object_list boundary: prove the
security check fires BEFORE any LLM call is made, so a malicious schema never even
touches the inference path. The LLM worker is mocked via pytest-mock — no inference
marker, runs in CI.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipeline.job_metadata import JobMetadata


def _make_stub_llm_assignment() -> LLMAssignment:
    return LLMAssignment(
        job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
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


class TestLLMGenerateSecurity:
    @pytest.mark.asyncio
    async def test_llm_gen_object_rejects_unsafe_schema_before_calling_worker(self, mocker: MockerFixture) -> None:
        """A malicious ObjectAssignment must raise UnsafeSchemaError before the LLM is invoked.

        This is the critical contract: a tampered schema must never reach the LLM call
        path, let alone consume inference budget.
        """
        mock_get_worker = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        assignment = ObjectAssignment(
            object_class_name="Innocent",
            object_class_schema=_malicious_schema(),
            llm_assignment_for_object=_make_stub_llm_assignment(),
        )
        with pytest.raises(UnsafeSchemaError):
            await llm_gen_object(assignment)
        mock_get_worker.return_value.gen_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_gen_object_list_rejects_unsafe_schema_before_calling_worker(self, mocker: MockerFixture) -> None:
        """Same contract for the list variant."""
        mock_get_worker = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        assignment = ObjectAssignment(
            object_class_name="Innocent",
            object_class_schema=_malicious_schema(),
            llm_assignment_for_object=_make_stub_llm_assignment(),
        )
        with pytest.raises(UnsafeSchemaError):
            await llm_gen_object_list(assignment)
        mock_get_worker.return_value.gen_object.assert_not_called()
