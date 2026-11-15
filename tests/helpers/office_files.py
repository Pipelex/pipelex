"""Minimal Office Open XML packages, for tests that judge or hand around an Office file without an Office library.

Each package is a zip holding only the `[Content_Types].xml` entry that names its main part, which is what a format
judgement reads, and an entry before it, so that a sniffer reading only the first entry would not recognise it.
"""

import io
import zipfile

XLSX_MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
DOCX_MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
PPTX_MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"

XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def office_package_bytes(*, main_content_type: str | None) -> bytes:
    """A zip whose content types name a main part of the given type, or a zip with no content types when None."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("docProps/app.xml", "<Properties/>")
        if main_content_type is not None:
            package.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                f'<Override PartName="/main.xml" ContentType="{main_content_type}"/>'
                "</Types>",
            )
    return buffer.getvalue()


def xlsx_bytes() -> bytes:
    return office_package_bytes(main_content_type=XLSX_MAIN_CONTENT_TYPE)


def docx_bytes() -> bytes:
    return office_package_bytes(main_content_type=DOCX_MAIN_CONTENT_TYPE)
