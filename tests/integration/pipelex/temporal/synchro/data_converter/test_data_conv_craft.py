import pytest

from pipelex import pretty_print
from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.hub import get_model_deck
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.temporal_data_converter import BaseModelPayloadConverter
from pipelex.temporal.test_extras.temporal_registry_test_models import Person

from .conftest import CraftingTestCases


@pytest.mark.temporal
class TestDataConverterForCrafting:
    def test_data_converter_for_make_llm_text(
        self,
        payload_converter: BaseModelPayloadConverter,
    ):
        user_text = CraftingTestCases.USER_TEXT_FOR_BASE
        llm_setting = get_model_deck().get_llm_setting(llm_choice="$testing-text")
        llm_prompt_for_text = LLMPrompt(user_text=user_text)
        llm_assignment = LLMAssignment(
            job_metadata=JobMetadata(user_id="test", pipeline_run_id="test"),
            llm_setting=llm_setting,
            llm_prompt=llm_prompt_for_text,
        )
        pretty_print(llm_assignment, title="llm_assignment")
        payload = payload_converter.to_payload(llm_assignment)
        pretty_print(payload, title="payload")
        assert payload
        restored: LLMAssignment = payload_converter.from_payload(payload, type_hint=LLMAssignment)
        pretty_print(restored, title="restored LLMAssignment")
        assert restored
        assert llm_assignment == restored

    def test_data_converter_for_make_object_direct(
        self,
        payload_converter: BaseModelPayloadConverter,
    ):
        user_text = CraftingTestCases.USER_TEXT_FOR_SINGLE_PERSON
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="$testing-structured")
        llm_prompt_for_object = LLMPrompt(user_text=user_text)
        llm_assignment_for_object = LLMAssignment(
            job_metadata=JobMetadata(user_id="test", pipeline_run_id="test"),
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=Person,
            llm_assignment=llm_assignment_for_object,
        )
        pretty_print(object_assignment, title="object_assignment")
        payload = payload_converter.to_payload(object_assignment)
        pretty_print(payload, title="payload")
        assert payload
        restored: ObjectAssignment = payload_converter.from_payload(payload, type_hint=ObjectAssignment)
        pretty_print(restored, title="restored ObjectAssignment")
        assert restored
        assert object_assignment == restored
