"""Run setup establishes the format of every file input once, and stamps it as the content's `mime_type`.

The bytes are the truth: a sniffed type replaces any declared one. A stored file is identified by a
head read of its first bytes, a data URL and a local file by the bytes already in hand. When the
bytes identify nothing (plain text, Markdown, HTML), the declared type stands. An http(s) input is
never fetched. Identification runs whether or not relocation to storage is enabled, and every file
input comes back with its path in the inputs (`transcripts[2]`, `case.attachment`) for messages.
"""

import asyncio
import base64
from pathlib import Path
from typing import Any

import pytest
from pydantic import Field
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.exceptions import PipelineInputContentError
from pipelex.pipeline.input_normalizer import (
    MAX_CONCURRENT_FILE_IDENTIFICATIONS,
    FileInputKind,
    collect_file_inputs,
    prepare_file_inputs,
)
from pipelex.tools.misc.filetype_utils import FILE_HEAD_NB_BYTES
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.uri.resolved_uri import UriKind

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_BYTES = Path("tests/data/documents/CV-ELIAS-THORNE.docx").read_bytes()
PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
PNG_BYTES = Path("tests/data/images/logo-tiny.png").read_bytes()
STORAGE_SCOPE = "test/scope"


class CaseFile(StructuredContent):
    """A structure holding a document among other fields, for the nested walk."""

    title: str = Field(description="The case title")
    attachment: DocumentContent = Field(description="The case attachment")


def _concept(code: NativeConceptCode) -> Any:
    return ConceptFactory.make_native_concept(native_concept_code=code)


def _memory(**contents: StuffContent) -> WorkingMemory:
    memory = WorkingMemoryFactory.make_empty()
    for name, content in contents.items():
        concept_code = NativeConceptCode.IMAGE if isinstance(content, ImageContent) else NativeConceptCode.DOCUMENT
        memory.add_new_stuff(name=name, stuff=StuffFactory.make_stuff(concept=_concept(concept_code), content=content, name=name))
    return memory


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


def _storage_root(tmp_path: Path) -> Path:
    return tmp_path / "storage"


def _stored_bytes(*, tmp_path: Path, uri: str) -> bytes:
    return (_storage_root(tmp_path) / uri.removeprefix("pipelex-storage://")).read_bytes()


def _stored_keys(*, tmp_path: Path) -> set[str]:
    root = _storage_root(tmp_path)
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def storage(mocker: MockerFixture, tmp_path: Path) -> LocalStorageProvider:
    """A real local storage provider, installed where the normalizer looks it up, with local uploads enabled."""
    provider = LocalStorageProvider(root_path=_storage_root(tmp_path))
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_config",
        return_value=mocker.Mock(runtime=mocker.Mock(storage=mocker.Mock(is_upload_local_content_enabled=True))),
    )
    return provider


@pytest.mark.asyncio(loop_scope="class")
class TestFileInputIdentification:
    async def test_a_stored_docx_without_mime_type_gets_stamped_from_a_head_read(self, storage: LocalStorageProvider, mocker: MockerFixture):
        uri = await storage.store(data=DOCX_BYTES, key="org/uploads/transcript.docx")
        head_spy = mocker.spy(storage, "load_head")
        full_load_spy = mocker.spy(storage, "load")
        memory = _memory(transcript=DocumentContent(url=uri))

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        content = memory.get_stuff("transcript").content
        assert isinstance(content, DocumentContent)
        assert content.url == uri
        assert content.mime_type == DOCX_MIME
        head_spy.assert_awaited_once_with(uri=uri, nb_bytes=FILE_HEAD_NB_BYTES)
        full_load_spy.assert_not_called()

    async def test_a_png_data_url_holding_a_pdf_is_corrected_to_pdf(self, storage: LocalStorageProvider, tmp_path: Path):  # ruff: ignore[unused-method-argument]
        memory = _memory(referral_letter=ImageContent(url=_data_url(mime_type="image/png", raw_bytes=PDF_BYTES)))

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        content = memory.get_stuff("referral_letter").content
        assert isinstance(content, ImageContent)
        assert content.mime_type == "application/pdf"
        assert content.url.startswith("pipelex-storage://test/scope/assets/")
        assert content.url.endswith(".pdf")
        assert _stored_bytes(tmp_path=tmp_path, uri=content.url) == PDF_BYTES

    async def test_an_unidentifiable_data_url_keeps_its_declared_type(self, storage: LocalStorageProvider, tmp_path: Path):  # ruff: ignore[unused-method-argument]
        """Plain text carries no signature: the declared type stands, where the sniff used to raise FileTypeError (a 500)."""
        markdown = b"# Notes\n\nNothing a sniffer can recognise."
        memory = _memory(notes=DocumentContent(url=_data_url(mime_type="text/markdown", raw_bytes=markdown)))

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        content = memory.get_stuff("notes").content
        assert isinstance(content, DocumentContent)
        assert content.mime_type == "text/markdown"
        assert content.url.endswith(".md")
        assert _stored_bytes(tmp_path=tmp_path, uri=content.url) == markdown

    async def test_an_http_url_is_never_fetched_and_keeps_its_declared_type(self, storage: LocalStorageProvider, mocker: MockerFixture):
        http_get = mocker.patch("httpx.AsyncClient.get")
        head_spy = mocker.spy(storage, "load_head")
        memory = _memory(
            page=DocumentContent(url="https://example.com/report", mime_type="text/html"), other=DocumentContent(url="https://example.com/x")
        )

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        page = memory.get_stuff("page").content
        other = memory.get_stuff("other").content
        assert isinstance(page, DocumentContent)
        assert isinstance(other, DocumentContent)
        assert page.mime_type == "text/html"
        assert other.mime_type is None
        http_get.assert_not_called()
        head_spy.assert_not_called()

    async def test_list_items_and_nested_fields_are_identified_with_their_paths(self, storage: LocalStorageProvider):
        docx_uri = await storage.store(data=DOCX_BYTES, key="org/uploads/a.docx")
        pdf_uri = await storage.store(data=PDF_BYTES, key="org/uploads/b.pdf")
        memory = _memory(
            transcripts=ListContent[DocumentContent](items=[DocumentContent(url=pdf_uri), DocumentContent(url=docx_uri)]),
        )
        memory.add_new_stuff(
            name="case",
            stuff=StuffFactory.make_stuff(
                concept=_concept(NativeConceptCode.TEXT),
                content=CaseFile(title="A case", attachment=DocumentContent(url=docx_uri)),
                name="case",
            ),
        )

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        file_inputs = {file_input.display_path: file_input for file_input in collect_file_inputs(memory)}
        assert set(file_inputs) == {"transcripts[0]", "transcripts[1]", "case.attachment"}
        assert file_inputs["transcripts[0]"].mime_type == "application/pdf"
        assert file_inputs["transcripts[0]"].format_key == "pdf"
        assert file_inputs["transcripts[1]"].format_key == "docx"
        assert file_inputs["transcripts[1]"].path == ("transcripts", 1)
        assert file_inputs["case.attachment"].format_key == "docx"
        assert file_inputs["case.attachment"].path == ("case", "attachment")
        assert file_inputs["case.attachment"].kind == FileInputKind.DOCUMENT
        assert file_inputs["case.attachment"].uri_kind == UriKind.PIPELEX_STORAGE
        case_content = memory.get_stuff("case").content
        assert isinstance(case_content, CaseFile)
        assert case_content.title == "A case"

    async def test_identification_runs_when_relocation_is_disabled(self, storage: LocalStorageProvider, tmp_path: Path):
        stored_uri = await storage.store(data=DOCX_BYTES, key="org/uploads/c.docx")
        local_pdf = tmp_path / "letter.pdf"
        local_pdf.write_bytes(PDF_BYTES)
        data_url = _data_url(mime_type="image/png", raw_bytes=PNG_BYTES)
        memory = _memory(
            stored=DocumentContent(url=stored_uri),
            local=DocumentContent(url=str(local_pdf)),
            inline=ImageContent(url=data_url),
        )

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=False)

        stored = memory.get_stuff("stored").content
        local = memory.get_stuff("local").content
        inline = memory.get_stuff("inline").content
        assert isinstance(stored, DocumentContent)
        assert isinstance(local, DocumentContent)
        assert isinstance(inline, ImageContent)
        assert stored.mime_type == DOCX_MIME
        assert local.mime_type == "application/pdf"
        assert inline.mime_type == "image/png"
        # Nothing was relocated: every url is the one given, and no public link was made.
        assert stored.url == stored_uri
        assert local.url == str(local_pdf)
        assert inline.url == data_url
        assert stored.public_url is None
        assert _stored_keys(tmp_path=tmp_path) == {"org/uploads/c.docx"}

    async def test_a_missing_stored_object_is_an_input_error(self, storage: LocalStorageProvider):  # ruff: ignore[unused-method-argument]
        memory = _memory(transcript=DocumentContent(url="pipelex-storage://org/uploads/never-uploaded.docx"))

        with pytest.raises(PipelineInputContentError, match="transcript"):
            await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

    async def test_stored_files_are_identified_concurrently_within_a_bound(self, storage: LocalStorageProvider, mocker: MockerFixture):
        nb_files = MAX_CONCURRENT_FILE_IDENTIFICATIONS * 3
        uris = [await storage.store(data=PDF_BYTES, key=f"org/uploads/{index}.pdf") for index in range(nb_files)]
        in_flight = 0
        peak_in_flight = 0
        original_load_head = storage.load_head

        async def _slow_load_head(uri: str, *, nb_bytes: int) -> bytes:
            nonlocal in_flight, peak_in_flight
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return await original_load_head(uri, nb_bytes=nb_bytes)

        mocker.patch.object(storage, "load_head", side_effect=_slow_load_head)
        memory = _memory(transcripts=ListContent[DocumentContent](items=[DocumentContent(url=uri) for uri in uris]))

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        assert peak_in_flight > 1, "the head reads overlap"
        assert peak_in_flight <= MAX_CONCURRENT_FILE_IDENTIFICATIONS, "and never more of them than the bound"
        assert all(file_input.format_key == "pdf" for file_input in collect_file_inputs(memory))
