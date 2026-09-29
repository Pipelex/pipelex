import base64
import io
import re
from functools import cache
from typing import NamedTuple

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image as PilImage
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutBlock, LayoutDocument, MarkdownBlock
from pipelex.cogt.doc_gen.render_job import RenderJob, RenderResources
from pipelex.providers.reportlab.reportlab_pdf_renderer import ReportlabPdfRenderer

TEST_FILENAME = "test-document.pdf"
TEST_TITLE = "Test document"


class ResourceRead(NamedTuple):
    uri: str
    position: str


class StubRenderResources(RenderResources):
    """Decodes `data:` URLs, or answers every read with `answer` when set, and records each read."""

    def __init__(self, *, answer: bytes | None = None):
        self.reads: list[ResourceRead] = []
        self._answer = answer

    @override
    def load(self, *, uri: str, position: str) -> bytes:
        self.reads.append(ResourceRead(uri=uri, position=position))
        if self._answer is not None:
            return self._answer
        header, _, payload = uri.partition(",")
        assert header.startswith("data:"), f"the stub reads data URLs only, not {uri[:40]}"
        assert header.endswith(";base64"), f"the stub reads base64 data URLs only, not {uri[:40]}"
        return base64.b64decode(payload)


@cache
def get_test_renderer() -> ReportlabPdfRenderer:
    return ReportlabPdfRenderer()


def render_layout(*, blocks: list[LayoutBlock], title: str = TEST_TITLE, resources: RenderResources | None = None) -> bytes:
    layout = LayoutDocument(title=title, blocks=blocks)
    job = RenderJob(format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, filename=TEST_FILENAME, title=title, layout=layout)
    rendered = get_test_renderer().render(job=job, resources=resources or StubRenderResources())
    return rendered.data


def render_markdown(*, markdown_text: str) -> bytes:
    return render_layout(blocks=[MarkdownBlock(markdown=markdown_text)])


def page_texts(*, pdf_data: bytes) -> list[str]:
    """The text of every page, its lines separated by line feeds."""
    pdf = pdfium.PdfDocument(pdf_data)
    try:
        texts: list[str] = []
        for page_index in range(len(pdf)):
            page_text: str = pdf[page_index].get_textpage().get_text_bounded()  # pyright: ignore[reportUnknownMemberType]
            texts.append(page_text.replace("\r\n", "\n"))
        return texts
    finally:
        pdf.close()


def document_text(*, pdf_data: bytes) -> str:
    return "\n".join(page_texts(pdf_data=pdf_data))


def pdf_title(*, pdf_data: bytes) -> str:
    pdf = pdfium.PdfDocument(pdf_data)
    try:
        return str(pdf.get_metadata_dict()["Title"])
    finally:
        pdf.close()


def image_count(*, pdf_data: bytes) -> int:
    """How many images the pages draw: ReportLab stores identical pixels once, so the file's image objects may be fewer."""
    pdf = pdfium.PdfDocument(pdf_data)
    try:
        count = 0
        for page_index in range(len(pdf)):
            page_images = pdf[page_index].get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            count += len(list(page_images))  # pyright: ignore[reportUnknownArgumentType]
        return count
    finally:
        pdf.close()


def link_targets(*, pdf_data: bytes) -> list[str]:
    """The target of every link annotation: ReportLab writes them uncompressed, as `/URI (target)`."""
    return [target.decode("latin-1") for target in re.findall(rb"/URI \(([^)]*)\)", pdf_data)]


def embedded_font_names(*, pdf_data: bytes) -> set[str]:
    """The base font names, without their subset prefix, such as 'OpenSans-Bold'."""
    return {name.decode("latin-1").split("+")[-1] for name in re.findall(rb"/BaseFont /([A-Za-z0-9+\-]+)", pdf_data)}


def png_bytes(*, width: int, height: int, color: tuple[int, int, int] = (40, 90, 200)) -> bytes:
    buffer = io.BytesIO()
    PilImage.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def png_data_url(*, width: int, height: int, color: tuple[int, int, int] = (40, 90, 200)) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(width=width, height=height, color=color)).decode("ascii")
