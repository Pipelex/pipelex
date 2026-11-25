import json
from typing import Any
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stored_value_storer import STORED_VALUE_PREVIEW_MAX_CHARS
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.storage.storage_file_name import STORAGE_FILE_EXTENSION_PATTERN, STORAGE_FILE_STEM_PATTERN
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.tools.uri.exceptions import UriReadRefusedError
from tests.integration.pipelex.pipeline.cases import LargeTextsStoredTestData

# No `from __future__ import annotations`: the function a `PipeFunc` calls has its annotations read when it is bound.
STORAGE_URI_SCHEME = "pipelex-storage://"


@pipe_func()
def large_texts_return_text(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument] - a PipeFunc's signature
    return TextContent(text=LargeTextsStoredTestData.FUNCTION_TEXT)


@pipe_func()
def large_texts_return_html(working_memory: WorkingMemory) -> HtmlContent:  # ruff: ignore[unused-function-argument] - a PipeFunc's signature
    return HtmlContent(inner_html=LargeTextsStoredTestData.FUNCTION_INNER_HTML)


@pipe_func()
def large_texts_return_json(working_memory: WorkingMemory) -> JSONContent:  # ruff: ignore[unused-function-argument] - a PipeFunc's signature
    return JSONContent(json_obj=LargeTextsStoredTestData.FUNCTION_JSON_OBJ)


@pipe_func()
def large_texts_echo_notes(working_memory: WorkingMemory) -> TextContent:
    """Read the notes synchronously, as a function does, which only a loaded stored value allows."""
    return TextContent(text=working_memory.get_stuff_as_text(name="notes").require_text())


class LongReportLLMWorker(LLMWorkerAbstract):
    """Answers every text generation with a long report."""

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        return LargeTextsStoredTestData.GENERATED_TEXT

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        msg = "This test generates texts only"
        raise NotImplementedError(msg)


def _long_report_worker() -> LongReportLLMWorker:
    inference_model = InferenceModelSpec(
        backend_name="stand_in",
        name="stand-in-llm",
        sdk="stand_in",
        model_type=ModelType.LLM,
        model_id="stand-in-llm-1",
        inputs=["text"],
        outputs=["text", "structured"],
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return LongReportLLMWorker(inference_model=inference_model, reporting_delegate=None)


def _run_storage_scope() -> str:
    """A storage scope of its own for each run, under the read scope, as a hosted run's is."""
    return f"{LargeTextsStoredTestData.READ_SCOPE}/mt_large_texts/run_{uuid4().hex}"


async def _execute(*, pipe_code: str, inputs: dict[str, Any], storage_scope: str, pipe_run_mode: PipeRunMode | None = None) -> PipeOutput:
    protocol = PipelexMTHDSProtocol(storage_scope=storage_scope, read_scope=LargeTextsStoredTestData.READ_SCOPE, pipe_run_mode=pipe_run_mode)
    result = await protocol.execute(pipe_code=pipe_code, mthds_contents=[LargeTextsStoredTestData.MTHDS], inputs=inputs)
    return result.pipe_output


def _stored_key(content: StoredValueContent) -> str:
    assert content.url is not None
    assert content.url.startswith(STORAGE_URI_SCHEME)
    return content.url.removeprefix(STORAGE_URI_SCHEME)


def _assert_key_is_readable_by_every_reader(*, key: str) -> None:
    """Every segment holds the characters the hosted platform's storage URI parser accepts, the last a stem and an extension."""
    *directory_segments, file_name = key.split("/")
    for segment in directory_segments:
        assert STORAGE_FILE_STEM_PATTERN.fullmatch(segment), key
    stem, extension = file_name.split(".")
    assert STORAGE_FILE_STEM_PATTERN.fullmatch(stem), key
    assert STORAGE_FILE_EXTENSION_PATTERN.fullmatch(extension), key


@pytest.mark.asyncio(loop_scope="class")
class TestLargeTextsStoredAtProduction:
    @pytest.mark.parametrize(
        ("pipe_code", "content_class", "stored_text", "mime_type", "extension"),
        [
            ("write_report", TextContent, LargeTextsStoredTestData.GENERATED_TEXT, "text/plain", "txt"),
            ("write_markdown_report", MarkdownContent, LargeTextsStoredTestData.GENERATED_TEXT, "text/markdown", "md"),
            ("return_text", TextContent, LargeTextsStoredTestData.FUNCTION_TEXT, "text/plain", "txt"),
            ("return_html", HtmlContent, LargeTextsStoredTestData.FUNCTION_INNER_HTML, "text/html", "html"),
            (
                "return_json",
                JSONContent,
                json.dumps(LargeTextsStoredTestData.FUNCTION_JSON_OBJ, ensure_ascii=False),
                "application/json",
                "json",
            ),
        ],
    )
    async def test_a_large_output_is_stored_where_it_is_produced(
        self,
        mocker: MockerFixture,
        pipe_code: str,
        content_class: type[StoredValueContent],
        stored_text: str,
        mime_type: str,
        extension: str,
    ) -> None:
        """A model's text and a function's text, HTML and JSON past the threshold leave the step as references to the run's storage."""
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=_long_report_worker())
        storage_scope = _run_storage_scope()

        pipe_output = await _execute(pipe_code=pipe_code, inputs={"topic": "the quarterly figures"}, storage_scope=storage_scope)

        output_content = pipe_output.main_stuff.content
        assert isinstance(output_content, content_class)
        assert output_content.is_stored
        key = _stored_key(output_content)
        assert key.startswith(f"{storage_scope}/generated/")
        assert key.endswith(f"/value.{extension}")
        _assert_key_is_readable_by_every_reader(key=key)
        assert output_content.mime_type == mime_type
        assert output_content.size == len(stored_text.encode("utf-8"))
        assert output_content.preview == stored_text[:STORED_VALUE_PREVIEW_MAX_CHARS]
        # The storage holds the whole value, and the process that stored it still reads it without a load.
        stored_bytes = await get_storage_provider().load(STORAGE_URI_SCHEME + key)
        assert stored_bytes.decode("utf-8") == stored_text
        assert output_content.stored_text() == stored_text
        # The value crosses every boundary as its reference only.
        assert stored_text not in pipe_output.main_stuff.model_dump_json(serialize_as_any=True)

        # The caller's text input was stored at intake, under the run's own assets.
        topic_content = pipe_output.working_memory.get_stuff(name="topic").content
        assert isinstance(topic_content, TextContent)
        topic_key = _stored_key(topic_content)
        assert topic_key.startswith(f"{storage_scope}/assets/")
        assert topic_key.endswith("/value.txt")
        _assert_key_is_readable_by_every_reader(key=topic_key)

    async def test_a_dry_run_stores_nothing(self) -> None:
        """A dry run's inputs and outputs stay inline whatever their size: its storage scope never reaches storage."""
        pipe_output = await _execute(
            pipe_code="write_report",
            inputs={"topic": "the quarterly figures"},
            storage_scope=_run_storage_scope(),
            pipe_run_mode=PipeRunMode.DRY,
        )

        output_content = pipe_output.main_stuff.content
        assert isinstance(output_content, TextContent)
        assert not output_content.is_stored
        topic_content = pipe_output.working_memory.get_stuff(name="topic").content
        assert isinstance(topic_content, TextContent)
        assert not topic_content.is_stored
        assert topic_content.require_text() == "the quarterly figures"

    @pytest.mark.parametrize(
        ("pipe_code", "expected_text"),
        [
            ("echo_notes", LargeTextsStoredTestData.CALLER_TEXT),
            ("quote_notes", f"Quoted: {LargeTextsStoredTestData.CALLER_TEXT}"),
        ],
    )
    async def test_a_caller_url_input_is_read_where_a_step_reads_it(self, pipe_code: str, expected_text: str) -> None:
        """A text the caller stored and gives by URL reaches a function and a template whole, read under the run's read scope."""
        notes_key = f"{LargeTextsStoredTestData.READ_SCOPE}/uploads/{uuid4().hex}/notes.txt"
        notes_url = await get_storage_provider().store(
            data=LargeTextsStoredTestData.CALLER_TEXT.encode("utf-8"), key=notes_key, content_type="text/plain; charset=utf-8"
        )

        pipe_output = await _execute(
            pipe_code=pipe_code,
            inputs={"notes": {"concept": "Text", "content": {"url": notes_url}}},
            storage_scope=_run_storage_scope(),
        )

        output_content = pipe_output.main_stuff.content
        assert isinstance(output_content, TextContent)
        assert output_content.require_text() == expected_text
        # The caller's reference is kept as given, never copied into the run's storage.
        notes_content = pipe_output.working_memory.get_stuff(name="notes").content
        assert isinstance(notes_content, TextContent)
        assert notes_content.url == notes_url

    async def test_a_caller_url_input_outside_the_read_scope_is_refused_naming_the_input(self) -> None:
        """A storage reference another tenant owns is refused at intake, before any step reads it."""
        foreign_url = f"{STORAGE_URI_SCHEME}another_org/uploads/{uuid4().hex}/notes.txt"

        with pytest.raises(PipelexError) as exc_info:
            await _execute(
                pipe_code="echo_notes",
                inputs={"notes": {"concept": "Text", "content": {"url": foreign_url}}},
                storage_scope=_run_storage_scope(),
            )

        refusals = [error for error in (exc_info.value, exc_info.value.__cause__) if isinstance(error, UriReadRefusedError)]
        assert refusals, repr(exc_info.value)
        assert "input 'notes'" in str(refusals[0])
        assert "another_org" not in str(refusals[0])
