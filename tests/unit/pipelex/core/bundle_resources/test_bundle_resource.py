import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.core.bundle_resources.bundle_resource import (
    canonical_resource_path,
    canonical_resource_path_or_none,
    canonical_submitted_files,
    path_refusal_params,
    root_escape_of,
)
from pipelex.core.bundle_resources.exceptions import BundleResourcePathError

# The parameters of each refusal: the security rule a path leaving the bundle breaks, or the request's field.
_ABSOLUTE = {"rule": "absolute"}
_PARENT_SEGMENT = {"rule": "parent_segment"}
_RESOURCES_FIELD = {"field": "resources"}


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
        ("path", "reason", "code", "params"),
        [
            ("", "empty", CoreCode.REQUEST_INVALID, _RESOURCES_FIELD),
            ("   ", "empty", CoreCode.REQUEST_INVALID, _RESOURCES_FIELD),
            (".", "names no file", CoreCode.REQUEST_INVALID, _RESOURCES_FIELD),
            ("/etc/invoice.docx", "absolute", CoreCode.SECURITY_INPUT_PATH_REFUSED, _ABSOLUTE),
            ("\\etc\\invoice.docx", "absolute", CoreCode.SECURITY_INPUT_PATH_REFUSED, _ABSOLUTE),
            ("../invoice.docx", "'..' segment", CoreCode.SECURITY_INPUT_PATH_REFUSED, _PARENT_SEGMENT),
            ("templates/../../invoice.docx", "'..' segment", CoreCode.SECURITY_INPUT_PATH_REFUSED, _PARENT_SEGMENT),
            ("..\\secrets\\key.pem", "'..' segment", CoreCode.SECURITY_INPUT_PATH_REFUSED, _PARENT_SEGMENT),
            ("C:/Windows/invoice.docx", "drive", CoreCode.SECURITY_INPUT_PATH_REFUSED, _ABSOLUTE),
            ("C:invoice.docx", "drive", CoreCode.SECURITY_INPUT_PATH_REFUSED, _ABSOLUTE),
            ("\\\\server\\share\\invoice.docx", "network share", CoreCode.SECURITY_INPUT_PATH_REFUSED, _ABSOLUTE),
            ("templates\\invoice.docx", "backslash", CoreCode.REQUEST_INVALID, _RESOURCES_FIELD),
            ("invoice:v2.docx", "colon", CoreCode.REQUEST_INVALID, _RESOURCES_FIELD),
            ("invoice\x00.docx", "NUL", CoreCode.REQUEST_INVALID, _RESOURCES_FIELD),
        ],
    )
    def test_a_path_that_cannot_name_a_file_inside_the_bundle_is_refused(
        self, path: str, reason: str, code: CoreCode, params: dict[str, str]
    ) -> None:
        """The message says why, the lenient form answers None, and only a path leaving the bundle is a security refusal.

        A security refusal names the rule the path broke, never the path; any other refusal names the request's field.
        """
        with pytest.raises(BundleResourcePathError) as exc_info:
            canonical_resource_path(path=path)
        assert reason in exc_info.value.message
        assert exc_info.value.resolve_error_code() == code
        assert exc_info.value.given_params == params
        assert path_refusal_params(path=path) == params
        escape = root_escape_of(path=path)
        assert (escape.rule if escape is not None else None) == params.get("rule")
        if escape is not None:
            # The one classifier gives both the message's reason and the security rule.
            assert escape.desc in exc_info.value.message
        assert canonical_resource_path_or_none(path=path) is None


class TestCanonicalSubmittedFiles:
    def test_files_are_keyed_by_their_canonical_path(self) -> None:
        files = canonical_submitted_files(files={"./invoice.docx": b"docx", "templates/report.html": b"<h1></h1>"})

        assert files == {"invoice.docx": b"docx", "templates/report.html": b"<h1></h1>"}

    def test_two_spellings_of_one_file_are_refused(self) -> None:
        with pytest.raises(BundleResourcePathError, match="name the same file") as exc_info:
            canonical_submitted_files(files={"invoice.docx": b"a", "./invoice.docx": b"b"})
        assert exc_info.value.resolve_error_code() == CoreCode.REQUEST_INVALID
        assert exc_info.value.given_params == _RESOURCES_FIELD
