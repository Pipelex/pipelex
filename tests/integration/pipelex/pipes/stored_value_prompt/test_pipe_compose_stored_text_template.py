from pathlib import Path
from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import (
    RecordingContentGenerator,
    make_text_memory,
    run_pipe_dry,
    stored_pages,
    text_inputs_read_by,
)
from tests.integration.pipelex.pipes.stored_value_prompt.test_data import STORED_TEXT, STORED_TEXT_URL

_SUBJECT = "the quarterly report"
_BUNDLES_DIR = Path("tests/integration/pipelex/pipes/stored_value_prompt/bundles")


@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeStoredTextTemplate:
    @pytest.mark.parametrize(
        ("blueprint_fields", "expected_output", "expected_nb_loads"),
        [
            pytest.param(
                {"template": "Digest of {{ subject.text }}:\n{{ pages.text }}", "output": NativeConceptCode.TEXT},
                {"text": f"Digest of {_SUBJECT}:\n{STORED_TEXT}"},
                1,
                id="the_template_reads_a_stored_text",
            ),
            pytest.param(
                {"template": "Digest of {{ subject.text }}", "output": NativeConceptCode.TEXT},
                {"text": f"Digest of {_SUBJECT}"},
                0,
                id="the_template_reads_inline_values_only",
            ),
            pytest.param(
                {
                    "construct": {"heading": {"template": "On {{ subject.text }}"}, "body": {"template": "{{ pages.text }}"}},
                    "output": "PagesDigest",
                },
                {"heading": f"On {_SUBJECT}", "body": STORED_TEXT},
                1,
                id="a_construct_template_field_reads_a_stored_text",
            ),
            pytest.param(
                {
                    "construct": {"heading": {"template": "On {{ subject.text }}"}, "body": {"template": "All about {{ subject.text }}"}},
                    "output": "PagesDigest",
                },
                {"heading": f"On {_SUBJECT}", "body": f"All about {_SUBJECT}"},
                0,
                id="a_construct_template_fields_read_inline_values_only",
            ),
        ],
    )
    async def test_the_templates_render_a_stored_text_in_full_and_load_only_what_they_read(
        self,
        mocker: MockerFixture,
        load_test_library: Callable[[list[Path]], None],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        blueprint_fields: dict[str, Any],
        expected_output: dict[str, str],
        expected_nb_loads: int,
    ) -> None:
        """A stored text a template reads is loaded once before rendering; templates reading only inline values dispatch nothing."""
        load_test_library([_BUNDLES_DIR])
        load_spy = mocker.spy(recording_content_generator, "load_stored_texts")
        pages = stored_pages()
        inputs = text_inputs_read_by(templates=[repr(blueprint_fields)])
        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="stored_value_readers",
            pipe_code="compose_the_pages",
            blueprint=PipeComposeBlueprint.model_validate(
                {"description": "Compose pages that may live in storage", "inputs": inputs, **blueprint_fields}
            ),
            concept_codes_from_the_same_domain=["PagesDigest"],
        )
        get_pipe_library().add_new_pipe(pipe)

        pipe_output = await run_pipe_dry(
            pipe=pipe,
            working_memory=make_text_memory(texts={"subject": TextContent(text=_SUBJECT), "pages": pages}),
            job_metadata=scoped_job_metadata,
        )

        assert pipe_output.main_stuff.content.smart_dump() == expected_output
        assert load_spy.call_count == expected_nb_loads
        if expected_nb_loads:
            assert [uri_reference.uri for uri_reference in load_spy.call_args.kwargs["uri_references"]] == [STORED_TEXT_URL]
        else:
            assert not pages.is_loaded
