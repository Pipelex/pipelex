"""Run setup refuses an Image input whose file is not an image, whatever will consume it.

The check needs no model: an Image holding a PDF is wrong for every consumer. It rides the setup's
identification walk, so it covers every listed and nested image and names the input by its path. It
fires only on a positive identification: an image the sniffer cannot identify, an SVG for one, is
left to its consumer. A refused file is refused before it is relocated, so nothing is stored for it.
"""

import base64
import io
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import Field
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.exceptions import PipelineInputNotAnImageError
from pipelex.pipeline.input_normalizer import prepare_file_inputs
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider

DOCX_BYTES = Path("tests/data/documents/CV-ELIAS-THORNE.docx").read_bytes()
PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
PNG_BYTES = Path("tests/data/images/logo-tiny.png").read_bytes()
JPEG_BYTES = Path("tests/data/images/eiffel_tower.jpg").read_bytes()
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
STORAGE_SCOPE = "test/scope"


class Patient(StructuredContent):
    """A structure holding an image among other fields, for the nested walk."""

    name: str = Field(description="The patient's name")
    scan: ImageContent = Field(description="The patient's scan")


def _memory(**contents: StuffContent) -> WorkingMemory:
    memory = WorkingMemoryFactory.make_empty()
    for name, content in contents.items():
        concept_code = NativeConceptCode.TEXT if isinstance(content, Patient) else NativeConceptCode.IMAGE
        memory.add_new_stuff(
            name=name,
            stuff=StuffFactory.make_stuff(concept=ConceptFactory.make_native_concept(native_concept_code=concept_code), content=content, name=name),
        )
    return memory


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


def _stored_keys(*, root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def storage(mocker: MockerFixture, tmp_path: Path) -> LocalStorageProvider:
    """A real local storage provider, installed where the normalizer looks it up, with local uploads enabled."""
    provider = LocalStorageProvider(root_path=tmp_path / "storage")
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_config",
        return_value=mocker.Mock(runtime=mocker.Mock(storage=mocker.Mock(is_upload_local_content_enabled=True))),
    )
    return provider


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerImageCheck:
    @pytest.mark.parametrize("is_relocation_enabled", [True, False])
    async def test_a_pdf_given_to_an_image_input_is_refused_naming_the_input(
        self,
        storage: LocalStorageProvider,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
        is_relocation_enabled: bool,
    ):
        """The data URL claims a PNG; its bytes are a PDF. Nothing is stored for the refused file."""
        memory = _memory(referral_letter=ImageContent(url=_data_url(mime_type="image/png", raw_bytes=PDF_BYTES)))

        with pytest.raises(PipelineInputNotAnImageError) as exc_info:
            await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=is_relocation_enabled)

        assert str(exc_info.value) == (
            "Input 'referral_letter' expects an image, but the file is a PDF document (.pdf). Give an image file such as PNG, JPEG or WebP."
        )
        assert not (tmp_path / "storage").exists() or _stored_keys(root=tmp_path / "storage") == set()

    async def test_an_archive_given_to_an_image_input_is_refused(self, storage: LocalStorageProvider):  # ruff: ignore[unused-method-argument]
        """A bare zip has no format of its own to report, but it is not an image whatever it holds."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("photos/readme.txt", "not a photo")
        memory = _memory(photo=ImageContent(url=_data_url(mime_type="image/png", raw_bytes=buffer.getvalue())))

        with pytest.raises(
            PipelineInputNotAnImageError,
            match=re.escape("Input 'photo' expects an image, but the file is a .zip file."),
        ):
            await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=False)

    async def test_a_stored_word_document_given_to_an_image_input_is_refused(self, storage: LocalStorageProvider):
        uri = await storage.store(data=DOCX_BYTES, key="org/uploads/photo.png")

        with pytest.raises(
            PipelineInputNotAnImageError,
            match=re.escape("Input 'photo' expects an image, but the file is a Word document (.docx)."),
        ):
            await prepare_file_inputs(_memory(photo=ImageContent(url=uri)), storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

    async def test_a_pdf_as_the_third_item_of_an_image_list_is_named_by_its_index(self, storage: LocalStorageProvider):
        png_uri = await storage.store(data=PNG_BYTES, key="org/uploads/a.png")
        jpeg_uri = await storage.store(data=JPEG_BYTES, key="org/uploads/b.jpg")
        pdf_uri = await storage.store(data=PDF_BYTES, key="org/uploads/c.png")
        photos = ListContent[ImageContent](items=[ImageContent(url=png_uri), ImageContent(url=jpeg_uri), ImageContent(url=pdf_uri)])

        with pytest.raises(PipelineInputNotAnImageError, match=r"Input 'photos\[2\]' expects an image, but the file is a PDF document"):
            await prepare_file_inputs(_memory(photos=photos), storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

    async def test_an_image_nested_in_a_structure_is_checked_by_its_path(self, storage: LocalStorageProvider):
        pdf_uri = await storage.store(data=PDF_BYTES, key="org/uploads/scan.png")
        memory = _memory(patient=Patient(name="Ada", scan=ImageContent(url=pdf_uri)))

        with pytest.raises(PipelineInputNotAnImageError, match=r"Input 'patient\.scan' expects an image"):
            await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

    async def test_real_images_pass(self, storage: LocalStorageProvider):
        png_uri = await storage.store(data=PNG_BYTES, key="org/uploads/a.png")
        memory = _memory(
            stored=ImageContent(url=png_uri),
            inline=ImageContent(url=_data_url(mime_type="image/jpeg", raw_bytes=JPEG_BYTES)),
        )

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        stored = memory.get_stuff("stored").content
        inline = memory.get_stuff("inline").content
        assert isinstance(stored, ImageContent)
        assert isinstance(inline, ImageContent)
        assert stored.mime_type == "image/png"
        assert inline.mime_type == "image/jpeg"

    @pytest.mark.parametrize(
        ("declared_mime_type", "expected_mime_type"),
        [
            ("image/svg+xml", "image/svg+xml"),
            (None, None),
        ],
    )
    async def test_an_unidentifiable_image_is_left_to_its_consumer(
        self, storage: LocalStorageProvider, declared_mime_type: str | None, expected_mime_type: str | None
    ):
        """An SVG carries no signature the sniffer reads: whatever was declared stands, and nothing is refused."""
        svg_uri = await storage.store(data=SVG_BYTES, key="org/uploads/drawing.svg")
        memory = _memory(drawing=ImageContent(url=svg_uri, mime_type=declared_mime_type))

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        drawing: Any = memory.get_stuff("drawing").content
        assert isinstance(drawing, ImageContent)
        assert drawing.mime_type == expected_mime_type

    async def test_an_http_image_is_not_checked(self, storage: LocalStorageProvider):  # ruff: ignore[unused-method-argument]
        """An http(s) input is never fetched, so its declared type is all setup knows, and setup does not refuse on a declaration alone."""
        memory = _memory(photo=ImageContent(url="https://example.com/letter.pdf", mime_type="application/pdf"))

        await prepare_file_inputs(memory, storage_scope=STORAGE_SCOPE, read_scope=None, is_relocation_enabled=True)

        photo = memory.get_stuff("photo").content
        assert isinstance(photo, ImageContent)
        assert photo.mime_type == "application/pdf"
