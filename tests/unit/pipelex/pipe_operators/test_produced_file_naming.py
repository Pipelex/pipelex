from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept
from pipelex.pipe_operators import produced_file_naming
from pipelex.pipe_operators.produced_file_naming import input_naming_context, name_produced_files, prepare_naming_context
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageNotConfiguredError
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError, UriTextNotUtf8Error, UriTextTooLargeError


def _image_stuff(*, name: str, url: str, filename: str | None = None) -> Stuff:
    return StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.IMAGE), content=ImageContent(url=url, filename=filename), name=name)


def _text_stuff(*, name: str, content: TextContent) -> Stuff:
    return StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.TEXT), content=content, name=name)


def _naming_job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test-user", pipeline_run_id="run"))


def _stored_text() -> TextContent:
    return TextContent(url="pipelex-storage://org/title.txt", size=9, mime_type="text/plain", preview="Big title")


@pytest.mark.asyncio(loop_scope="class")
class TestProducedFileNaming:
    @pytest.fixture(autouse=True)
    def empty_library(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()

    @pytest.mark.parametrize(
        "template",
        [
            "{{ title.text | wordwrap(0) }}",
            "{{ '{:d}'.format('a') }}",
            "{{ title.__class__ }}",
            "{{ title.text.missing }}",
            "{% for %}",
        ],
        ids=["filter_value_error", "format_value_error", "sandbox_refusal", "undefined", "syntax_error"],
    )
    async def test_a_failing_template_keeps_the_runtime_name(self, template: str) -> None:
        """Naming a file never fails a run: whatever the template raises, the file keeps the runtime's name."""
        title = _text_stuff(name="title", content=TextContent(text="Report"))
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([title, output], main_name="cover")

        await name_produced_files(output_filename=template, main_stuff=output, naming_context=input_naming_context(memory=memory), pipe_code="draw")

        assert isinstance(output.content, ImageContent)
        assert output.content.filename == "abc.png"

    async def test_a_stored_input_the_template_reads_falls_back_when_it_cannot_be_loaded(self) -> None:
        """A stored text never loaded cannot be read by the template: the file keeps its runtime name, the step goes on."""
        title = _text_stuff(name="title", content=_stored_text())
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([title, output], main_name="cover")

        await name_produced_files(
            output_filename="{{ title }}", main_stuff=output, naming_context=input_naming_context(memory=memory), pipe_code="draw"
        )

        assert isinstance(output.content, ImageContent)
        assert output.content.filename == "abc.png"

    async def test_a_loaded_stored_input_names_the_file(self) -> None:
        """Once its stored value is loaded, a stored text renders as its value."""
        stored = _stored_text()
        stored.accept_loaded_text(text="Big title")
        title = _text_stuff(name="title", content=stored)
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([title, output], main_name="cover")

        await name_produced_files(
            output_filename="{{ title }}", main_stuff=output, naming_context=input_naming_context(memory=memory), pipe_code="draw"
        )

        assert isinstance(output.content, ImageContent)
        assert output.content.filename == "Big title.png"

    async def test_an_output_named_like_an_input_does_not_shadow_it(self) -> None:
        """The context is taken from the inputs before the step writes its output, even under the same name."""
        source = _image_stuff(name="photo", url="https://example.com/in.png", filename="holiday.png")
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([source], main_name="photo")
        naming_context = input_naming_context(memory=memory)
        produced = _image_stuff(name="photo", url="https://example.com/out.png", filename="generated.png")
        memory.set_new_main_stuff(stuff=produced, name="photo")

        await name_produced_files(output_filename="edited {{ photo.filename }}", main_stuff=produced, naming_context=naming_context, pipe_code="edit")

        assert isinstance(produced.content, ImageContent)
        assert produced.content.filename == "edited holiday.png"

    async def test_the_context_is_a_snapshot_of_the_inputs(self, mocker: MockerFixture) -> None:
        """Writing to the memory after the snapshot leaves the context as it was."""
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([_text_stuff(name="title", content=TextContent(text="A"))])
        naming_context = input_naming_context(memory=memory)
        memory.add_new_stuff(name="later", stuff=_text_stuff(name="later", content=TextContent(text="B")))
        spy = mocker.spy(produced_file_naming, "render_jinja2_async")
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")

        await name_produced_files(output_filename="{{ title }}", main_stuff=output, naming_context=naming_context, pipe_code="draw")

        assert "later" not in spy.call_args.kwargs["templating_context"]
        assert isinstance(output.content, ImageContent)
        assert output.content.filename == "A.png"

    @pytest.mark.parametrize("load_fails", [False, True], ids=["loaded", "refused"])
    async def test_the_stored_values_the_template_reads_are_loaded_before_naming(self, mocker: MockerFixture, load_fails: bool) -> None:
        """The template's stored inputs are loaded through the leaf; a refused load leaves the file its runtime name."""
        stored = _stored_text()
        title = _text_stuff(name="title", content=stored)
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([title])

        def load(**kwargs: object) -> int:  # ruff: ignore[unused-function-argument]
            if load_fails:
                msg = "refused"
                raise UriReadRefusedError(msg, reason=UriReadRefusalReason.FOREIGN_STORAGE_KEY)
            stored.accept_loaded_text(text="Big title")
            return 1

        loader = mocker.patch.object(produced_file_naming, "load_stored_values_read_from_memory", new=mocker.AsyncMock(side_effect=load))
        naming_context = await prepare_naming_context(
            output_filename="{{ title }} cover",
            working_memory=memory,
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test-user", pipeline_run_id="run")
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            pipe_code="draw",
        )
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")
        await name_produced_files(output_filename="{{ title }} cover", main_stuff=output, naming_context=naming_context, pipe_code="draw")

        assert loader.call_args.kwargs["read_paths"] == frozenset({"title"})
        assert isinstance(output.content, ImageContent)
        assert output.content.filename == ("abc.png" if load_fails else "Big title cover.png")

    @pytest.mark.parametrize(
        "read_failure",
        [
            UriTextTooLargeError("too large", limit=10, size=20, input_name="title"),
            UriTextNotUtf8Error("not UTF-8", input_name="title"),
            StorageNotConfiguredError("no storage"),
            StorageFileNotFoundError("gone"),
            RemoteFileFetchError("the server answered HTTP 503"),
        ],
        ids=["oversized", "not_utf8", "storage_not_configured", "stored_file_missing", "remote_fetch_failed"],
    )
    async def test_a_stored_input_that_cannot_be_read_leaves_the_runtime_name(self, mocker: MockerFixture, read_failure: Exception) -> None:
        """Every documented way a stored text fails to read leaves the file its runtime name, with a warning, and the step goes on."""
        title = _text_stuff(name="title", content=_stored_text())
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([title])
        mocker.patch.object(produced_file_naming, "load_stored_values_read_from_memory", new=mocker.AsyncMock(side_effect=read_failure))

        naming_context = await prepare_naming_context(
            output_filename="{{ title }} cover",
            working_memory=memory,
            job_metadata=_naming_job_metadata(),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            pipe_code="draw",
        )
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")
        await name_produced_files(output_filename="{{ title }} cover", main_stuff=output, naming_context=naming_context, pipe_code="draw")

        assert isinstance(output.content, ImageContent)
        assert output.content.filename == "abc.png"

    async def test_a_stored_input_whose_bytes_are_not_utf8_leaves_the_runtime_name(self) -> None:
        """Read for real through the content generator's leaf: a text given as bytes that are not UTF-8 names nothing."""
        title = _text_stuff(name="title", content=TextContent(url="data:text/plain;base64,//79", mime_type="text/plain", size=3, preview="?"))
        memory = WorkingMemoryFactory.make_from_multiple_stuffs([title])

        naming_context = await prepare_naming_context(
            output_filename="{{ title }} cover",
            working_memory=memory,
            job_metadata=_naming_job_metadata(),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            pipe_code="draw",
        )
        output = _image_stuff(name="cover", url="https://example.com/files/abc.png")
        await name_produced_files(output_filename="{{ title }} cover", main_stuff=output, naming_context=naming_context, pipe_code="draw")

        assert isinstance(output.content, ImageContent)
        assert output.content.filename == "abc.png"
