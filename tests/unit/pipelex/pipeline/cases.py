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
            "a_data_url_that_is_not_base64",
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
