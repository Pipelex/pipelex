from typing import Any, cast

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.search_generate import search_gen_structured, search_gen_structured_object
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.stored_value_content import STORED_VALUE_REFERENCE_FIELDS
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class SearchTopic(TextContent):
    """A concept refining Text, as a method declares one."""


class SearchFinding(StructuredContent):
    """A structured search output holding stored-value contents."""

    headline: SearchTopic
    summary: TextContent
    data: JSONContent


class SchemaCapturingSearchWorker:
    """A search worker that writes the schema it would show the model, as a provider does, and answers with a finding."""

    def __init__(self) -> None:
        self.captured_schemas: list[dict[str, Any]] = []

    async def search_structured(self, *, search_job: SearchJob, schema: type[BaseModel]) -> dict[str, Any]:
        _ = search_job
        self.captured_schemas.append(schema.model_json_schema())
        return {"headline": {"text": "Pipelex"}, "summary": {"text": "A runtime for methods"}, "data": {"json_obj": {"stars": 1}}}


def _search_assignment() -> SearchAssignment:
    return SearchAssignment(
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_search_schema")),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        query="what is pipelex?",
        search_setting=SearchSetting(model="mock-search-handle"),
    )


def _object_definitions(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every object schema in a JSON schema, its root included, by name."""
    definitions = cast("dict[str, dict[str, Any]]", dict(schema.get("$defs", {})))
    definitions["<root>"] = schema
    return definitions


class TestSearchGenerateSchema:
    @pytest.mark.parametrize("arm", ["in_process", "boundary"])
    @pytest.mark.asyncio
    async def test_the_provider_sees_a_stored_value_content_as_its_value_alone(self, mocker: MockerFixture, arm: str) -> None:
        """Both structured-search arms hand the provider a schema asking for the value, required, and never for a url."""
        worker = SchemaCapturingSearchWorker()
        mocker.patch("pipelex.cogt.content_generation.search_generate._make_search_worker", return_value=worker)
        mocker.patch("pipelex.cogt.content_generation.search_generate._make_search_job", return_value=mocker.MagicMock())
        search_assignment = _search_assignment()

        match arm:
            case "in_process":
                finding = await search_gen_structured_object(search_assignment, output_class=SearchFinding)
                assert finding.headline.text == "Pipelex"
                assert finding.data.json_obj == {"stars": 1}
            case _:
                result_dict = await search_gen_structured(SearchObjectAssignment.make_for_class(SearchFinding, search_assignment=search_assignment))
                assert result_dict["headline"] == {"text": "Pipelex"}

        assert len(worker.captured_schemas) == 1
        stored_value_definitions = {
            name: definition
            for name, definition in _object_definitions(worker.captured_schemas[0]).items()
            if {"text", "json_obj"} & set(definition.get("properties", {}))
        }
        # The rebuilt boundary class may inline the definitions, so the count is not pinned: at least the value forms are there.
        assert stored_value_definitions
        for definition in stored_value_definitions.values():
            assert not set(STORED_VALUE_REFERENCE_FIELDS) & set(definition["properties"])
            value_field_name = "json_obj" if "json_obj" in definition["properties"] else "text"
            assert value_field_name in definition["required"]
            assert "anyOf" not in definition["properties"][value_field_name]
