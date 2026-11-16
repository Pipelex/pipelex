from typing import Any, cast

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.dry_mock import dry_llm_gen_object, dry_llm_gen_object_list
from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_object
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.stored_value_content import STORED_VALUE_REFERENCE_FIELDS
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class Topic(TextContent):
    """A concept refining Text, as a method declares one."""


class Briefing(StructuredContent):
    """A structure holding stored-value contents at depth."""

    headline: Topic
    notes: list[TextContent]
    data: JSONContent


def _object_assignment(*, object_class: type[StructuredContent] | type[TextContent], nb_items: int | None = None) -> ObjectAssignment:
    llm_assignment = LLMAssignment(
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_schema")),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
        llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
        llm_prompt=LLMPrompt(),
    )
    return ObjectAssignment.make_for_class(object_class=object_class, llm_assignment=llm_assignment, nb_items=nb_items)


def _definitions(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every object schema in a JSON schema, its root included, by name."""
    definitions = cast("dict[str, dict[str, Any]]", dict(schema.get("$defs", {})))
    definitions["<root>"] = schema
    return definitions


class TestStoredValueGenerationSchema:
    @pytest.mark.parametrize("object_class", [Topic, Briefing])
    def test_the_generation_schema_asks_for_the_value_and_never_the_reference(
        self, object_class: type[StructuredContent] | type[TextContent]
    ) -> None:
        """A model, and a leaf rebuilding the class, see a stored-value content as its value alone, required."""
        schema = _object_assignment(object_class=object_class).object_class_schema

        stored_value_definitions = {
            name: definition for name, definition in _definitions(schema).items() if {"text", "json_obj"} & set(definition.get("properties", {}))
        }
        assert stored_value_definitions
        for definition in stored_value_definitions.values():
            assert not set(STORED_VALUE_REFERENCE_FIELDS) & set(definition["properties"])
            value_field_name = "json_obj" if "json_obj" in definition["properties"] else "text"
            assert value_field_name in definition["required"]
            assert "anyOf" not in definition["properties"][value_field_name]

    def test_the_class_s_own_schema_keeps_both_forms(self) -> None:
        """Outside a generation, such as for a pipe's input contract, a text still holds its value or a URL to it."""
        _object_assignment(object_class=Topic)

        assert set(STORED_VALUE_REFERENCE_FIELDS) <= set(Topic.model_json_schema()["properties"])

    def test_a_dry_mock_rebuilt_from_the_schema_revalidates_into_the_real_class(self, mocker: MockerFixture) -> None:
        """The boundary arm rebuilds the class from the schema, mocks it, and the workflow validates the mock into the real class."""
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate")
        for _ in range(10):
            raw_topic = dry_llm_gen_object(_object_assignment(object_class=Topic), object_class=None)
            raw_briefings = dry_llm_gen_object_list(_object_assignment(object_class=Briefing, nb_items=3), object_class=None)

            topic = revalidate_leaf_object(raw_topic, object_class=Topic, is_mock_built=True, dump_mode="json")
            briefings = [
                revalidate_leaf_object(raw_briefing, object_class=Briefing, is_mock_built=True, dump_mode="json") for raw_briefing in raw_briefings
            ]

            assert topic.text is not None
            assert topic.url is None
            assert len(briefings) == 3
            for briefing in briefings:
                assert briefing.headline.text is not None
                assert briefing.headline.url is None
                assert briefing.data.json_obj is not None
