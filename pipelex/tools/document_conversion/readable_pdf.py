"""The PDF a step reads in place of an Office file, and where that PDF is kept.

**Where a PDF is kept.** Beside its source when the source is in storage, at `<source key>.pdf` with the source's
extension lowercased, the key the platform's preview worker writes (`pdf_key_of` in pipelex-server's
`pipelex_shared.domain.doc_conversions`), so a file converted for its preview is not converted again for a run, nor the
other way round. A source outside storage, an http(s) URL, a local path or a data URL, has no key to stand beside: its
PDF goes under the run's storage scope, named by the source's SHA-256 and format key, `<storage scope>/<sha256>.<format
key>.pdf`, so every step of the run that reads the same file converts it once, and a purge of the run erases it. The
two-dot name keeps either PDF out of a hosted run's files, since the platform's storage-URI parser refuses a final
segment whose stem holds a dot.

**What a kept PDF carries.** The object metadata `converter-version` and `export-options: printed-pages`, written with
the PDF, create-only. A kept PDF is reused whatever its version, and the version is what the trace records.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_PDF_SUFFIX = ".pdf"


class PdfOrigin(StrEnum):
    """Whether a step's PDF was found kept beside its source, or made by a conversion the step ran."""

    KEPT = "kept"
    MADE = "made"


class ReadablePdf(BaseModel):
    """The PDF a step reads in place of an Office file, and what a trace says about it.

    It crosses a process boundary on a host runtime, from the leaf that converts back to the step, so it carries the
    PDF's URI and never its bytes.
    """

    model_config = ConfigDict(frozen=True)

    pdf_uri: str
    """The `pipelex-storage://` URI of the PDF."""
    origin: PdfOrigin = Field(strict=False)
    converter_name: str | None
    """The backend that made the PDF, `gotenberg` or `soffice`; None for a kept PDF, whose metadata does not name it."""
    converter_version: str | None
    """The `converter-version` the PDF is stamped with; None for a kept PDF a provider keeping no metadata holds."""
    page_count: int = Field(ge=0)
    """The PDF's number of pages, what a step reading it is billed on."""
    conversion_seconds: float | None
    """How long the conversion took, None when the PDF was kept."""


def pdf_key_of(*, source_key: str) -> str:
    """The key of the PDF of the source at `source_key`: beside it, its extension lowercased.

    The same rule as the platform's `pdf_key_of`, so the runtime and the preview worker read and write one object.
    """
    stem, dot, extension = source_key.rpartition(".")
    if not dot:
        return f"{source_key}{_PDF_SUFFIX}"
    return f"{stem}.{extension.lower()}{_PDF_SUFFIX}"


def scoped_pdf_key(*, storage_scope: str, source_sha256: str, format_key: str) -> str:
    """The key of the PDF of a source outside storage, under the run's storage scope: `<scope>/<sha256>.<format key>.pdf`."""
    return f"{storage_scope}/{source_sha256}.{format_key.lower()}{_PDF_SUFFIX}"
