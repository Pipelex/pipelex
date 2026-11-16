from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import (
    RecordingContentGenerator,
    make_text_memory,
    run_pipe_dry,
    stored_pages,
    text_inputs_read_by,
)
from tests.integration.pipelex.pipes.stored_value_prompt.test_data import STORED_TEXT, STORED_TEXT_URL

_SUBJECT = "a lighthouse at dusk"


@pytest.mark.asyncio(loop_scope="class")
class TestPipeImgGenStoredTextPrompt:
    @pytest.mark.parametrize(
        ("prompt", "negative_prompt", "expected_prompt", "expected_negative_prompt", "expected_nb_loads"),
        [
            pytest.param(
                "Paint what these pages describe:\n{{ pages.text }}",
                None,
                f"Paint what these pages describe:\n{STORED_TEXT}",
                None,
                1,
                id="the_prompt_reads_a_stored_text",
            ),
            pytest.param(
                "Paint {{ subject.text }}",
                "Nothing of {{ pages.text }}",
                f"Paint {_SUBJECT}",
                f"Nothing of {STORED_TEXT}",
                1,
                id="the_negative_prompt_reads_a_stored_text",
            ),
            pytest.param(
                "Paint {{ subject.text }}",
                "Nothing blurry about {{ subject.text }}",
                f"Paint {_SUBJECT}",
                f"Nothing blurry about {_SUBJECT}",
                0,
                id="both_prompts_read_inline_values_only",
            ),
        ],
    )
    async def test_the_prompts_render_a_stored_text_in_full_and_load_only_what_they_read(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        prompt: str,
        negative_prompt: str | None,
        expected_prompt: str,
        expected_negative_prompt: str | None,
        expected_nb_loads: int,
    ) -> None:
        """A stored text a prompt reads is loaded once before rendering; a step reading only inline values dispatches nothing."""
        load_empty_library()
        load_spy = mocker.spy(recording_content_generator, "load_stored_texts")
        execution_data_spy = mocker.spy(PipeImgGen, "_register_execution_data")
        pages = stored_pages()
        inputs = text_inputs_read_by(templates=[prompt, negative_prompt])
        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="stored_value_prompt",
            pipe_code="paint_the_pages",
            blueprint=PipeImgGenBlueprint(
                description="Paint pages that may live in storage",
                inputs=inputs,
                output=NativeConceptCode.IMAGE,
                prompt=prompt,
                negative_prompt=negative_prompt,
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        await run_pipe_dry(
            pipe=pipe,
            working_memory=make_text_memory(texts={"subject": TextContent(text=_SUBJECT), "pages": pages}),
            job_metadata=scoped_job_metadata,
        )

        execution_data: dict[str, Any] = execution_data_spy.call_args.kwargs["execution_data"]
        assert execution_data["rendered_prompt"] == expected_prompt
        assert execution_data["rendered_negative_prompt"] == expected_negative_prompt
        assert load_spy.call_count == expected_nb_loads
        if expected_nb_loads:
            assert [uri_reference.uri for uri_reference in load_spy.call_args.kwargs["uri_references"]] == [STORED_TEXT_URL]
        else:
            assert not pages.is_loaded
