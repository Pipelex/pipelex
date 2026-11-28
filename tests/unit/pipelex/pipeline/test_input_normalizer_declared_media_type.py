import pytest
from pytest_mock import AsyncMockType, MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import PipelineInputContentError
from pipelex.pipeline.input_normalizer import prepare_file_inputs
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from tests.unit.pipelex.pipeline.cases import DeclaredMediaTypeCases, DeclaredTypeRefusalCase

STORAGE_SCOPE = "org_abc/run_1"
STORED_URI = "pipelex-storage://org_abc/run_1/assets/stored.txt"


def _memory_with_document(*, url: str, mime_type: str | None) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DOCUMENT),
        content=DocumentContent(url=url, mime_type=mime_type),
        name="notes",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _memory_with_value(*, content: StoredValueContent, native_concept_code: NativeConceptCode) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=native_concept_code), content=content, name="notes"
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _patch_storage(mocker: MockerFixture) -> AsyncMockType:
    """A storage that records what it is asked to store, and links nothing; the recording `store` is returned."""
    storage = mocker.Mock(spec=StorageProviderAbstract)
    store: AsyncMockType = mocker.AsyncMock(return_value=STORED_URI)
    storage.store = store
    storage.public_url = mocker.AsyncMock(return_value=None)
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=storage)
    return store


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerDeclaredMediaType:
    @pytest.mark.parametrize(
        ("_topic", "url", "mime_type", "expected_content_type", "expected_extension"), DeclaredMediaTypeCases.STORED_UNDER_BARE_TYPE
    )
    async def test_a_stored_data_url_is_stored_under_its_bare_type(
        self, mocker: MockerFixture, _topic: str, url: str, mime_type: str | None, expected_content_type: str, expected_extension: str
    ) -> None:
        store = _patch_storage(mocker)
        working_memory = await prepare_file_inputs(
            _memory_with_document(url=url, mime_type=mime_type), storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True
        )

        store_call = store.await_args
        assert store_call is not None
        assert store_call.kwargs["data"] == b"hello"
        assert store_call.kwargs["content_type"] == expected_content_type
        assert store_call.kwargs["key"].startswith(f"{STORAGE_SCOPE}/assets/")
        assert store_call.kwargs["key"].endswith(f".{expected_extension}")
        content = working_memory.get_stuff(name="notes").content
        assert isinstance(content, DocumentContent)
        assert content.url == STORED_URI
        assert content.mime_type == expected_content_type

    @pytest.mark.parametrize(("_topic", "url", "mime_type", "expected_mime_type", "_extension"), DeclaredMediaTypeCases.STORED_UNDER_BARE_TYPE)
    async def test_a_kept_data_url_carries_its_bare_type(
        self, mocker: MockerFixture, _topic: str, url: str, mime_type: str | None, expected_mime_type: str, _extension: str
    ) -> None:
        store = _patch_storage(mocker)
        working_memory = await prepare_file_inputs(
            _memory_with_document(url=url, mime_type=mime_type), storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=False
        )

        store.assert_not_awaited()
        content = working_memory.get_stuff(name="notes").content
        assert isinstance(content, DocumentContent)
        assert content.url == url
        assert content.mime_type == expected_mime_type

    @pytest.mark.parametrize("read_scope", [None, "org_abc"])
    @pytest.mark.parametrize(("_topic", "case"), DeclaredMediaTypeCases.REFUSED)
    async def test_a_declaration_that_is_not_one_media_type_is_refused_naming_its_field(
        self, mocker: MockerFixture, _topic: str, case: DeclaredTypeRefusalCase, read_scope: str | None
    ) -> None:
        """The refusal is the caller's to fix, names the field at fault, and never quotes the declaration."""
        store = _patch_storage(mocker)

        with pytest.raises(PipelineInputContentError) as exc_info:
            await prepare_file_inputs(
                _memory_with_document(url=case.url, mime_type=case.mime_type),
                storage_scope=STORAGE_SCOPE,
                read_scope=read_scope,
                is_relocation_enabled=True,
            )

        store.assert_not_awaited()
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == "input.file_unreadable"
        assert caller.params is not None
        wire_params = caller.params.as_wire()
        assert {name: wire_params.get(name) for name in ("input", "file_type", "reason")} == {
            "input": "notes",
            "file_type": "document",
            "reason": case.expected_reason,
        }
        assert caller.location is not None
        assert caller.location.model_dump(exclude_none=True) == {"input": "notes", "field": f"notes.{case.expected_field_suffix}"}
        message = str(exc_info.value)
        assert "text/plain" not in message
        assert "application/pdf" not in message

    @pytest.mark.parametrize("read_scope", [None, "org_abc"])
    @pytest.mark.parametrize(
        ("_topic", "content", "native_concept_code", "expected_file_type"),
        [
            ("a text given as a data URL that is not base64", TextContent(url="data:text/plain,hello"), NativeConceptCode.TEXT, "text"),
            ("a text given as a data URL in upper case", TextContent(url="DATA:text/plain,hello"), NativeConceptCode.TEXT, "text"),
            ("a JSON value given as a data URL that is not base64", JSONContent(url="data:application/json,{}"), NativeConceptCode.JSON, "json"),
        ],
    )
    async def test_a_value_given_as_a_data_url_that_is_not_base64_is_refused_naming_its_url(
        self,
        mocker: MockerFixture,
        _topic: str,
        content: StoredValueContent,
        native_concept_code: NativeConceptCode,
        expected_file_type: str,
        read_scope: str | None,
    ) -> None:
        """A value the run would read later is refused before the run starts, whatever its read scope."""
        _patch_storage(mocker)

        with pytest.raises(PipelineInputContentError) as exc_info:
            await prepare_file_inputs(
                _memory_with_value(content=content, native_concept_code=native_concept_code),
                storage_scope=STORAGE_SCOPE,
                read_scope=read_scope,
                is_relocation_enabled=True,
            )

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == "input.file_unreadable"
        assert caller.params is not None
        wire_params = caller.params.as_wire()
        assert {name: wire_params.get(name) for name in ("input", "file_type", "reason")} == {
            "input": "notes",
            "file_type": expected_file_type,
            "reason": "invalid_data_url",
        }
        assert caller.location is not None
        assert caller.location.model_dump(exclude_none=True) == {"input": "notes", "field": "notes.url"}
        assert "hello" not in str(exc_info.value)

    async def test_a_value_given_as_a_base64_data_url_is_kept_for_the_run_to_read(self, mocker: MockerFixture) -> None:
        _patch_storage(mocker)
        content = TextContent(url="data:text/plain;base64,aGVsbG8=")

        working_memory = await prepare_file_inputs(
            _memory_with_value(content=content, native_concept_code=NativeConceptCode.TEXT),
            storage_scope=STORAGE_SCOPE,
            read_scope=None,
            is_relocation_enabled=True,
        )

        prepared = working_memory.get_stuff(name="notes").content
        assert isinstance(prepared, TextContent)
        assert prepared.url == "data:text/plain;base64,aGVsbG8="
