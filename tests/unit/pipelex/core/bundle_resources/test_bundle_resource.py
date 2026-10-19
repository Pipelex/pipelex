import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.core.bundle_resources.bundle_resource import (
    canonical_resource_path,
    canonical_resource_path_or_none,
    canonical_submitted_files,
)
from pipelex.core.bundle_resources.exceptions import BundleResourcePathError


class TestCanonicalResourcePath:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("invoice.docx", "invoice.docx"),
            ("./invoice.docx", "invoice.docx"),
            ("templates//invoice.docx", "templates/invoice.docx"),
            ("templates/./invoice.docx", "templates/invoice.docx"),
            ("templates/invoice.docx/", "templates/invoice.docx"),
        ],
    )
    def test_a_relative_path_inside_the_bundle_has_one_spelling(self, path: str, expected: str) -> None:
        """`.` segments and repeated slashes collapse, so two spellings of one file are one key."""
        assert canonical_resource_path(path=path) == expected
        assert canonical_resource_path_or_none(path=path) == expected

    @pytest.mark.parametrize(
        ("path", "reason", "code"),
        [
            ("", "empty", CoreCode.REQUEST_INVALID),
            ("   ", "empty", CoreCode.REQUEST_INVALID),
            (".", "names no file", CoreCode.REQUEST_INVALID),
            ("/etc/invoice.docx", "absolute", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("\\etc\\invoice.docx", "absolute", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("../invoice.docx", "'..' segment", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("templates/../../invoice.docx", "'..' segment", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("..\\secrets\\key.pem", "'..' segment", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("C:/Windows/invoice.docx", "drive", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("C:invoice.docx", "drive", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("\\\\server\\share\\invoice.docx", "network share", CoreCode.SECURITY_INPUT_PATH_REFUSED),
            ("templates\\invoice.docx", "backslash", CoreCode.REQUEST_INVALID),
            ("invoice:v2.docx", "colon", CoreCode.REQUEST_INVALID),
            ("invoice\x00.docx", "NUL", CoreCode.REQUEST_INVALID),
        ],
    )
    def test_a_path_that_cannot_name_a_file_inside_the_bundle_is_refused(self, path: str, reason: str, code: CoreCode) -> None:
        """The message says why, the lenient form answers None, and only a path leaving the bundle is a security refusal."""
        with pytest.raises(BundleResourcePathError) as exc_info:
            canonical_resource_path(path=path)
        assert reason in exc_info.value.message
        assert exc_info.value.resolve_error_code() == code
        assert canonical_resource_path_or_none(path=path) is None


class TestCanonicalSubmittedFiles:
    def test_files_are_keyed_by_their_canonical_path(self) -> None:
        files = canonical_submitted_files(files={"./invoice.docx": b"docx", "templates/report.html": b"<h1></h1>"})

        assert files == {"invoice.docx": b"docx", "templates/report.html": b"<h1></h1>"}

    def test_two_spellings_of_one_file_are_refused(self) -> None:
        with pytest.raises(BundleResourcePathError, match="name the same file"):
            canonical_submitted_files(files={"invoice.docx": b"a", "./invoice.docx": b"b"})
