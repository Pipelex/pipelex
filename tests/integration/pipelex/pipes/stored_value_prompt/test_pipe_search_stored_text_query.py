from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.stored_value_prompt.cases import STORED_TEXT, STORED_TEXT_URL
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import RecordingContentGenerator, make_text_memory, run_pipe_dry, stored_pages

_SUBJECT = "tide tables for Brest"


@pytest.mark.asyncio(loop_scope="class")
class TestPipeSearchStoredTextQuery:
    @pytest.mark.parametrize(
        ("prompt", "inputs", "expected_query", "expected_nb_loads"),
        [
            pytest.param(
                "Find sources for:\n{{ pages.text }}",
                {"pages": NativeConceptCode.TEXT},
                f"Find sources for:\n{STORED_TEXT}",
                1,
                id="the_query_reads_a_stored_text",
            ),
            pytest.param(
                "Find {{ subject.text }}",
                {"subject": NativeConceptCode.TEXT},
                f"Find {_SUBJECT}",
                0,
                id="the_query_reads_an_inline_value_only",
            ),
        ],
    )
    async def test_the_query_renders_a_stored_text_in_full_and_loads_only_what_it_reads(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        prompt: str,
        inputs: dict[str, str],
        expected_query: str,
        expected_nb_loads: int,
    ) -> None:
        """A stored text the query reads is loaded once before rendering; a query reading only inline values dispatches nothing."""
        load_empty_library()
        load_spy = mocker.spy(recording_content_generator, "load_stored_texts")
        execution_data_spy = mocker.spy(PipeSearch, "_register_execution_data")
        pages = stored_pages()
        pipe = PipeFactory[PipeSearch].make_from_blueprint(
            domain_code="stored_value_prompt",
            pipe_code="search_the_pages",
            blueprint=PipeSearchBlueprint(
                description="Search for what pages that may live in storage say",
                inputs=inputs,
                output=NativeConceptCode.SEARCH_RESULT,
                prompt=prompt,
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        await run_pipe_dry(
            pipe=pipe,
            working_memory=make_text_memory(texts={"subject": TextContent(text=_SUBJECT), "pages": pages}),
            job_metadata=scoped_job_metadata,
        )

        execution_data: dict[str, Any] = execution_data_spy.call_args.kwargs["execution_data"]
        assert execution_data["rendered_query"] == expected_query
        assert load_spy.call_count == expected_nb_loads
        if expected_nb_loads:
            assert [uri_reference.uri for uri_reference in load_spy.call_args.kwargs["uri_references"]] == [STORED_TEXT_URL]
        else:
            assert not pages.is_loaded
