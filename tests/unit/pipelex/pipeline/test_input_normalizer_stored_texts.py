import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.exceptions import PipelineInputUrlMissingError
from pipelex.pipeline.input_normalizer import prepare_file_inputs
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError

READ_SCOPE = "org_abc"
STORAGE_SCOPE = "org_abc/mt_1/run_1"
LONG_TEXT = "A long text input, one line after another.\n" * 10


def _memory_with(*, concept_code: NativeConceptCode, content: StoredValueContent) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=concept_code),
        content=content,
        name="notes",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _patch_storage(mocker: MockerFixture, *, inline_max_bytes: int = 64) -> InMemoryStorageProvider:
    storage = InMemoryStorageProvider()
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=storage)
    mocker.patch("pipelex.core.stuffs.stored_value_storer.inline_text_max_bytes", return_value=inline_max_bytes)
    return storage


def _notes_content(working_memory: WorkingMemory) -> StoredValueContent:
    content = working_memory.get_stuff(name="notes").content
    assert isinstance(content, StoredValueContent)
    return content


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerStoredTexts:
    @pytest.mark.parametrize(
        ("concept_code", "content", "extension"),
        [
            (NativeConceptCode.TEXT, TextContent(text=LONG_TEXT), "txt"),
            (NativeConceptCode.HTML, HtmlContent(inner_html=f"<p>{LONG_TEXT}</p>"), "html"),
            (NativeConceptCode.JSON, JSONContent(json_obj={"notes": LONG_TEXT}), "json"),
        ],
    )
    async def test_a_large_input_is_stored_under_the_run_s_assets(
        self, mocker: MockerFixture, concept_code: NativeConceptCode, content: StoredValueContent, extension: str
    ):
        storage = _patch_storage(mocker)
        working_memory = _memory_with(concept_code=concept_code, content=content.model_copy(deep=True))

        await prepare_file_inputs(working_memory, storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, is_relocation_enabled=True)

        notes = _notes_content(working_memory)
        assert notes.is_stored
        assert notes.url is not None
        assert notes.url.startswith(f"pipelex-storage://{STORAGE_SCOPE}/assets/")
        assert notes.url.endswith(f"/value.{extension}")
        assert list(storage.root) == [notes.url.removeprefix("pipelex-storage://")]

    @pytest.mark.parametrize(
        ("topic", "text", "is_relocation_enabled", "is_dry_run"),
        [
            ("a small input", "short notes", True, False),
            ("a run that relocates nothing", LONG_TEXT, False, False),
            ("a dry run", LONG_TEXT, True, True),
        ],
    )
    async def test_an_input_stays_inline_when_it_need_not_be_stored(
        self, mocker: MockerFixture, topic: str, text: str, is_relocation_enabled: bool, is_dry_run: bool
    ):
        storage = _patch_storage(mocker)
        working_memory = _memory_with(concept_code=NativeConceptCode.TEXT, content=TextContent(text=text))

        await prepare_file_inputs(
            working_memory,
            storage_scope=STORAGE_SCOPE,
            read_scope=READ_SCOPE,
            is_relocation_enabled=is_relocation_enabled,
            is_dry_run=is_dry_run,
        )

        notes = _notes_content(working_memory)
        assert not notes.is_stored, topic
        assert notes.stored_text() == text, topic
        assert storage.root == {}, topic

    async def test_a_caller_url_under_the_read_scope_is_kept_as_given_and_read_nothing(self, mocker: MockerFixture):
        storage = _patch_storage(mocker)
        load_spy = mocker.spy(InMemoryStorageProvider, "load_with_metadata")
        caller_url = f"pipelex-storage://{READ_SCOPE}/uploads/notes.txt"
        working_memory = _memory_with(concept_code=NativeConceptCode.TEXT, content=TextContent(url=caller_url))

        await prepare_file_inputs(working_memory, storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, is_relocation_enabled=True)

        assert _notes_content(working_memory).url == caller_url
        load_spy.assert_not_called()
        assert storage.root == {}

    async def test_a_caller_url_outside_the_read_scope_is_refused_naming_the_input(self, mocker: MockerFixture):
        _patch_storage(mocker)
        foreign_url = "pipelex-storage://org_other/uploads/notes.txt"
        working_memory = _memory_with(concept_code=NativeConceptCode.TEXT, content=TextContent(url=foreign_url))

        with pytest.raises(UriReadRefusedError) as exc_info:
            await prepare_file_inputs(working_memory, storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, is_relocation_enabled=True)

        assert exc_info.value.reason == UriReadRefusalReason.FOREIGN_STORAGE_KEY
        assert "input 'notes'" in str(exc_info.value)
        assert "org_other" not in str(exc_info.value)

    async def test_a_blank_caller_url_is_refused(self, mocker: MockerFixture):
        _patch_storage(mocker)
        working_memory = _memory_with(concept_code=NativeConceptCode.TEXT, content=TextContent(url="  "))

        with pytest.raises(PipelineInputUrlMissingError):
            await prepare_file_inputs(working_memory, storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, is_relocation_enabled=True)

    async def test_a_caller_s_large_input_is_left_untouched_and_each_run_stores_it_under_its_own_scope(self, mocker: MockerFixture):
        """The content a caller passes is never changed: each run stores a copy, under its own scope, so a second run reads its own key."""
        storage = _patch_storage(mocker)
        callers_text = TextContent(text=LONG_TEXT)
        second_storage_scope = "org_xyz/mt_2/run_2"

        first_memory = _memory_with(concept_code=NativeConceptCode.TEXT, content=callers_text)
        await prepare_file_inputs(first_memory, storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, is_relocation_enabled=True)
        second_memory = _memory_with(concept_code=NativeConceptCode.TEXT, content=callers_text)
        await prepare_file_inputs(second_memory, storage_scope=second_storage_scope, read_scope="org_xyz", is_relocation_enabled=True)

        assert callers_text.text == LONG_TEXT
        assert not callers_text.is_stored
        first_notes = _notes_content(first_memory)
        second_notes = _notes_content(second_memory)
        assert first_notes is not callers_text
        assert second_notes is not callers_text
        assert first_notes.url is not None
        assert second_notes.url is not None
        assert first_notes.url.startswith(f"pipelex-storage://{STORAGE_SCOPE}/assets/")
        assert second_notes.url.startswith(f"pipelex-storage://{second_storage_scope}/assets/")
        assert first_notes.stored_text() == LONG_TEXT
        assert second_notes.stored_text() == LONG_TEXT
        assert sorted(storage.root) == sorted(url.removeprefix("pipelex-storage://") for url in (first_notes.url, second_notes.url))
