import hashlib
from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_generation import LLMTextGeneration
from pipelex.cogt.llm.llm_prompt_trace import TRACED_PROMPT_TEXT_MAX_BYTES, PromptTextPreview
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import RecordingContentGenerator
from tests.integration.pipelex.pipes.stored_value_prompt.test_data import STORAGE_SCOPE, STORED_TEXT, STORED_TEXT_URL, StoredValuePromptTestData


def _make_pipe(*, prompt: str, inputs: dict[str, str], output: str = NativeConceptCode.TEXT) -> PipeLLM:
    pipe = PipeFactory[PipeLLM].make_from_blueprint(
        domain_code="stored_value_prompt",
        pipe_code="read_the_pages",
        blueprint=PipeLLMBlueprint(description="Read pages that may live in storage", inputs=inputs, output=output, prompt=prompt),
    )
    get_pipe_library().add_new_pipe(pipe)
    return pipe


def _pages_content(*, is_stored: bool) -> TextContent:
    if is_stored:
        return TextContent.model_validate(StoredValuePromptTestData.TEXT_REFERENCE)
    return TextContent(text=STORED_TEXT)


def _make_memory(*, pages_content: TextContent, with_images: bool = False, with_unrelated: bool = False) -> WorkingMemory:
    stuffs = [StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.TEXT), content=pages_content, name="pages")]
    if with_images:
        for image_name in ("photo", "sketch"):
            stuffs.append(
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=ImageContent(url=f"https://example.com/{image_name}.png"),
                    name=image_name,
                )
            )
    if with_unrelated:
        stuffs.append(
            StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="a value the prompt never reads"),
                name="unrelated",
            )
        )
    return WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs, main_name="pages")


async def _run_dry(*, pipe: PipeLLM, working_memory: WorkingMemory, job_metadata: JobMetadata) -> None:
    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        job_metadata=job_metadata,
        working_memory=working_memory,
    )
    await get_pipe_router().run(pipe_job=pipe_job)


def _traced_user_prompt(*, execution_data_spy: Any) -> str:
    execution_data: dict[str, Any] = execution_data_spy.call_args.kwargs["execution_data"]
    rendered_user_prompt = execution_data["rendered_user_prompt"]
    assert isinstance(rendered_user_prompt, str)
    return rendered_user_prompt


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMStoredTextPrompt:
    async def test_a_stored_input_renders_in_full_and_the_trace_records_that_prompt(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
    ) -> None:
        """A direct run loads the stored text in the leaf, renders it whole, and the trace records the leaf's prompt."""
        load_empty_library()
        execution_data_spy = mocker.spy(PipeLLM, "_register_execution_data")
        pipe = _make_pipe(prompt="Summarize these pages:\n{{ pages.text }}", inputs={"pages": NativeConceptCode.TEXT})

        await _run_dry(pipe=pipe, working_memory=_make_memory(pages_content=_pages_content(is_stored=True)), job_metadata=scoped_job_metadata)

        assert _traced_user_prompt(execution_data_spy=execution_data_spy) == f"Summarize these pages:\n{STORED_TEXT}"
        assert len(recording_content_generator.crossed_prompts) == 1

    async def test_a_filter_on_a_stored_text_acts_on_the_real_text(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,  # ruff: ignore[unused-method-argument] - scopes the generator
    ) -> None:
        """`upper` and `length` see the loaded text, never the reference standing for it."""
        load_empty_library()
        execution_data_spy = mocker.spy(PipeLLM, "_register_execution_data")
        pipe = _make_pipe(prompt="{{ pages.text | upper }}\n{{ pages.text | length }}", inputs={"pages": NativeConceptCode.TEXT})

        await _run_dry(pipe=pipe, working_memory=_make_memory(pages_content=_pages_content(is_stored=True)), job_metadata=scoped_job_metadata)

        assert _traced_user_prompt(execution_data_spy=execution_data_spy) == f"{STORED_TEXT.upper()}\n{len(STORED_TEXT)}"

    async def test_image_numbering_is_unchanged_beside_a_stored_text(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
    ) -> None:
        """A prompt with inline images and a stored text numbers and hands over its images as the inline-text one does."""
        load_empty_library()
        make_llm_text_spy = mocker.spy(recording_content_generator, "make_llm_text")
        inputs: dict[str, str] = {"pages": NativeConceptCode.TEXT, "photo": NativeConceptCode.IMAGE, "sketch": NativeConceptCode.IMAGE}
        pipe = _make_pipe(prompt="First $photo, then $sketch, against these pages:\n{{ pages.text }}", inputs=inputs)

        rendered_by_form: dict[bool, LLMTextGeneration] = {}
        for is_stored in (False, True):
            await _run_dry(
                pipe=pipe,
                working_memory=_make_memory(pages_content=_pages_content(is_stored=is_stored), with_images=True),
                job_metadata=scoped_job_metadata,
            )
            text_generation = make_llm_text_spy.spy_return
            assert isinstance(text_generation, LLMTextGeneration)
            rendered_by_form[is_stored] = text_generation

        inline_prompt = rendered_by_form[False].rendered_prompt
        stored_prompt = rendered_by_form[True].rendered_prompt
        assert stored_prompt.traced_user_text == inline_prompt.traced_user_text
        assert stored_prompt.traced_user_text is not None
        assert "[Image 1]" in stored_prompt.traced_user_text
        assert "[Image 2]" in stored_prompt.traced_user_text
        assert stored_prompt.traced_user_text.index("[Image 1]") < stored_prompt.traced_user_text.index("[Image 2]")
        assert [str(image) for image in stored_prompt.user_images] == [str(image) for image in inline_prompt.user_images]
        assert len(stored_prompt.user_images) == 2

    @pytest.mark.parametrize(
        ("output", "entry_point"),
        [
            (NativeConceptCode.TEXT, "make_llm_text"),
            (NativeConceptCode.NUMBER, "make_object"),
        ],
    )
    async def test_the_llm_entry_points_receive_the_template_and_a_context_still_referenced(
        self,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        output: str,
        entry_point: str,
    ) -> None:
        """What crosses the protocol, which is what crosses a host runtime's activity boundary, carries the reference only."""
        load_empty_library()
        pipe = _make_pipe(prompt="Count the pages in:\n{{ pages.text }}", inputs={"pages": NativeConceptCode.TEXT}, output=output)

        await _run_dry(
            pipe=pipe,
            working_memory=_make_memory(pages_content=_pages_content(is_stored=True), with_unrelated=True),
            job_metadata=scoped_job_metadata,
        )

        assert len(recording_content_generator.crossed_prompts) == 1
        crossed_prompt = recording_content_generator.crossed_prompts[0]
        assert crossed_prompt.entry_point == entry_point
        # The template crosses unrendered, and the stored text as its reference, never loaded before the leaf.
        assert "Count the pages in:\\n{{ pages.text }}" in crossed_prompt.wire_dump
        assert STORED_TEXT_URL in crossed_prompt.wire_dump
        assert STORED_TEXT not in crossed_prompt.wire_dump
        assert STORED_TEXT[:200] not in crossed_prompt.wire_dump
        assert crossed_prompt.nb_stored_values == 1
        assert crossed_prompt.nb_unloaded_stored_values == 1
        # Only the stuffs the prompt reads cross: a value of the run's memory the template never names stays behind.
        assert crossed_prompt.context_names == {"pages"}

    async def test_a_prompt_larger_than_the_trace_bound_comes_back_as_a_preview(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        stored_text_storage: InMemoryStorageProvider,
    ) -> None:
        """A stored text loaded in the leaf never comes back whole: the result carries a preview with the size and digest."""
        load_empty_library()
        large_text = "a long page the leaf loads in full, and the trace keeps only the start of.\n" * (2 * TRACED_PROMPT_TEXT_MAX_BYTES // 64)
        large_text_key = f"{STORAGE_SCOPE}/generated/4567cdef/large_pages.txt"
        stored_text_storage.root[large_text_key] = large_text.encode("utf-8")
        large_reference = TextContent.model_validate(
            {
                "url": f"pipelex-storage://{large_text_key}",
                "size": len(large_text.encode("utf-8")),
                "mime_type": "text/plain",
                "preview": large_text[:40],
            }
        )
        make_llm_text_spy = mocker.spy(recording_content_generator, "make_llm_text")
        execution_data_spy = mocker.spy(PipeLLM, "_register_execution_data")
        pipe = _make_pipe(prompt="Summarize these pages:\n{{ pages.text }}", inputs={"pages": NativeConceptCode.TEXT})

        await _run_dry(pipe=pipe, working_memory=_make_memory(pages_content=large_reference), job_metadata=scoped_job_metadata)

        text_generation = make_llm_text_spy.spy_return
        assert isinstance(text_generation, LLMTextGeneration)
        full_prompt = f"Summarize these pages:\n{large_text}".encode()
        traced_user_text = text_generation.rendered_prompt.user_text
        assert isinstance(traced_user_text, PromptTextPreview)
        assert traced_user_text.size == len(full_prompt)
        assert traced_user_text.sha256 == hashlib.sha256(full_prompt).hexdigest()
        assert len(traced_user_text.preview.encode("utf-8")) <= TRACED_PROMPT_TEXT_MAX_BYTES
        # What crosses back, which a host runtime records in the workflow's history, does not hold the loaded text.
        assert large_text not in text_generation.model_dump_json(serialize_as_any=True)
        assert _traced_user_prompt(execution_data_spy=execution_data_spy) == traced_user_text.as_trace_text()
