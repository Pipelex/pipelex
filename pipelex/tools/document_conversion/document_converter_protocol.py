"""The runtime's document converter: an Office file in, its PDF out, behind one protocol and two backends.

A step whose model cannot read an Office file, or that asks for page views, reads the file's PDF instead; this seam
makes that PDF. `GotenbergConverter` posts the file to a Gotenberg container, which is what a server reading other
people's files runs, as the hosted plane does; `SofficeConverter` runs LibreOffice's `soffice` on this machine, for a
developer's machine and the tests, and is no isolation boundary. Which one a process uses is
`[runtime.document_conversion]`, off by default, and the hub hands it out with `get_optional_document_converter()`.

A PDF made here is a printed-pages export, LibreOffice's default: a workbook prints as it would on paper, a hidden
sheet left out. The platform's preview worker makes the same export and stamps its PDFs with the metadata below, so a
PDF made for a preview and one made for a run are one object, kept beside its source at `<source key>.pdf`.

The names here are the runtime's, never the MTHDS standard's: the standard says only that a `Document` may be a PDF
or an Office file.
"""

from typing import Protocol

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

# The format keys of the files the runtime converts, lowercase: the Office Open XML trio, the legacy binary formats and
# OpenDocument. The same set as the platform's `CONVERTIBLE_EXTENSIONS` (pipelex-server's
# `pipelex_shared.domain.doc_conversions`), so a file the platform previews is a file a run can convert.
CONVERTIBLE_FORMAT_KEYS: frozenset[str] = frozenset({"docx", "xlsx", "pptx", "doc", "xls", "ppt", "odt", "ods", "odp"})

# The object metadata a kept PDF carries, keys lowercase as S3 reads them back: what made the PDF, and which export.
PDF_METADATA_CONVERTER_VERSION = "converter-version"
PDF_METADATA_EXPORT_OPTIONS = "export-options"
# The one export a converted PDF is, printed pages.
EXPORT_OPTIONS_PRINTED_PAGES = "printed-pages"

PDF_MAGIC = b"%PDF-"


def is_convertible_format_key(*, format_key: str) -> bool:
    """Whether a file of this format key, whatever its case, is one the runtime converts to a PDF."""
    return format_key.lower() in CONVERTIBLE_FORMAT_KEYS


@dataclass(frozen=True, config=ConfigDict(strict=True))
class ConvertedPdf:
    """The PDF a converter made of a file, and what made it.

    It never crosses a process boundary: the step that converts writes the PDF to storage and hands on its URI.
    """

    pdf_bytes: bytes
    # The backend that converted it, `gotenberg` or `soffice`.
    converter_name: str
    # The version of the converter that made it, the `converter-version` the kept PDF is stamped with: for Gotenberg the
    # `Gotenberg-Version` header of the answer that carried the PDF, for `soffice` what `soffice --version` printed.
    converter_version: str


class DocumentConverterProtocol(Protocol):
    """Converts one Office file to a PDF of its printed pages.

    Every failure is one of `pipelex.tools.document_conversion.exceptions`: the file unreadable or too large, too
    slow included, or the converter unavailable. A backend retries what its converter's answers say is worth a retry
    before raising, and the step that converts retries nothing.
    """

    @property
    def converter_name(self) -> str:
        """The backend's name, `gotenberg` or `soffice`."""
        ...

    async def convert_to_pdf(self, *, data: bytes, format_key: str) -> ConvertedPdf:
        """The PDF of `data`, an Office file of the format `format_key`, one of `CONVERTIBLE_FORMAT_KEYS`.

        Raises:
            DocumentUnreadableByConverterError: The converter could not read the file.
            DocumentTooLargeToConvertError: The file is past the converter's size, or its conversion ran out of time.
            DocumentConverterUnavailableError: The converter is busy or unreachable.
            DocumentConverterAnswerError: The converter answered something that is not a PDF, or a PDF it named no
                version for.
        """
        ...
