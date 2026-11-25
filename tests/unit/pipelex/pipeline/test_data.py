import base64
from typing import Any, ClassVar, NamedTuple

from pipelex.core.concepts.native.concept_native import NativeConceptCode


class FileInputRefusalCase(NamedTuple):
    """A list input whose second file is refused, the run's read scope, and how the refusal names the input."""

    native_concept_code: NativeConceptCode
    input_name: str
    refused_url: str
    read_scope: str | None
    expected_code: str
    expected_params: dict[str, Any]


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


class InputRefusalNamingTestData:
    """File-input refusals that each name the root input as `input` and the path down to the file as the location's `field`."""

    FINE_URL = "https://example.com/a.pdf"
    # The leading bytes of a PDF file, which a sniff identifies as one.
    PDF_HEAD = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    MISSING_STORED_FILE = "pipelex-storage://org_abc/assets/missing.pdf"
    UNREADABLE_LOCAL_PATH = "/nonexistent-pipelex-test-directory/nope.pdf"

    CASES: ClassVar[list[tuple[str, FileInputRefusalCase]]] = [
        (
            "a_storage_reference_naming_nothing",
            FileInputRefusalCase(
                native_concept_code=NativeConceptCode.DOCUMENT,
                input_name="documents",
                refused_url=MISSING_STORED_FILE,
                read_scope=None,
                expected_code="input.reference_not_found",
                expected_params={"input": "documents"},
            ),
        ),
        (
            "a_data_url_whose_payload_is_not_base64",
            FileInputRefusalCase(
                native_concept_code=NativeConceptCode.DOCUMENT,
                input_name="documents",
                refused_url="data:application/pdf;base64,abc",
                read_scope=None,
                expected_code="input.file_unreadable",
                expected_params={"input": "documents", "file_type": "document", "reason": "invalid_base64"},
            ),
        ),
        (
            "a_local_path_that_cannot_be_read",
            FileInputRefusalCase(
                native_concept_code=NativeConceptCode.DOCUMENT,
                input_name="documents",
                refused_url=UNREADABLE_LOCAL_PATH,
                read_scope=None,
                expected_code="input.file_unreadable",
                expected_params={"input": "documents", "file_type": "document", "reason": "path_unreadable"},
            ),
        ),
        (
            "a_local_path_a_scoped_run_may_not_read",
            FileInputRefusalCase(
                native_concept_code=NativeConceptCode.DOCUMENT,
                input_name="documents",
                refused_url=UNREADABLE_LOCAL_PATH,
                read_scope="org_abc",
                expected_code="security.input_url_refused",
                expected_params={"input": "documents"},
            ),
        ),
    ]

    # An Image input holding a PDF, refused before any model reads it, so its `model` is never known (see the test's marker).
    IMAGE_HOLDING_A_PDF = FileInputRefusalCase(
        native_concept_code=NativeConceptCode.IMAGE,
        input_name="photos",
        refused_url=_data_url(mime_type="image/png", raw_bytes=PDF_HEAD),
        read_scope=None,
        expected_code="input.file_type_unsupported",
        expected_params={"input": "photos", "format": "pdf"},
    )


class DeclaredTypeRefusalCase(NamedTuple):
    """A file input whose declaration is refused, and the field and reason the refusal names."""

    url: str
    mime_type: str | None
    expected_field_suffix: str
    expected_reason: str


class DeclaredMediaTypeTestData:
    """File inputs whose declared media type is read as its bare type, or refused when it is not one media type."""

    HELLO_BASE64 = base64.b64encode(b"hello").decode("ascii")

    # A data URL whose header declares a type with parameters, stored under its bare type with the matching key extension.
    STORED_UNDER_BARE_TYPE: ClassVar[list[tuple[str, str, str | None, str, str]]] = [
        ("header_with_a_charset", f"data:text/plain;charset=utf-8;base64,{HELLO_BASE64}", None, "text/plain", "txt"),
        ("header_in_upper_case", f"DATA:Text/Plain;BASE64,{HELLO_BASE64}", None, "text/plain", "txt"),
        ("field_with_parameters", f"data:;base64,{HELLO_BASE64}", "text/plain; charset=utf-8", "text/plain", "txt"),
        ("header_wins_over_the_field", f"data:text/markdown;base64,{HELLO_BASE64}", "text/plain", "text/markdown", "md"),
    ]

    REFUSED: ClassVar[list[tuple[str, DeclaredTypeRefusalCase]]] = [
        (
            "a_data_url_that_is_not_base64",
            DeclaredTypeRefusalCase(url="data:text/plain,hello", mime_type=None, expected_field_suffix="url", expected_reason="invalid_data_url"),
        ),
        (
            "a_header_holding_a_comma",
            DeclaredTypeRefusalCase(
                url=f"data:application/pdf;,text/plain;base64,{HELLO_BASE64}",
                mime_type=None,
                expected_field_suffix="url",
                expected_reason="invalid_data_url",
            ),
        ),
        (
            "a_header_with_no_comma",
            DeclaredTypeRefusalCase(
                url=f"data:text/plain;base64{HELLO_BASE64}", mime_type=None, expected_field_suffix="url", expected_reason="invalid_data_url"
            ),
        ),
        (
            "a_header_declaring_no_subtype",
            DeclaredTypeRefusalCase(
                url=f"data:text;base64,{HELLO_BASE64}", mime_type=None, expected_field_suffix="url", expected_reason="invalid_data_url"
            ),
        ),
        (
            "a_mime_type_field_holding_a_comma",
            DeclaredTypeRefusalCase(
                url=f"data:;base64,{HELLO_BASE64}",
                mime_type="application/pdf,text/plain",
                expected_field_suffix="mime_type",
                expected_reason="invalid_media_type",
            ),
        ),
        (
            "a_mime_type_field_of_a_web_link_declaring_no_subtype",
            DeclaredTypeRefusalCase(
                url="https://example.com/notes.txt", mime_type="text", expected_field_suffix="mime_type", expected_reason="invalid_media_type"
            ),
        ),
    ]
