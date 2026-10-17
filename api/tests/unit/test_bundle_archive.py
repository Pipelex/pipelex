"""Unit tests for `pipelex_api.bundle` — decoding a `bundle_b64` archive under its guards.

Covers the archive's own guards: the encoded-length check before decoding, invalid base64, a
corrupt zip, an empty archive, the member-count ceiling and the zip-bomb bounded decompression.
The names of the entries it returns are judged by the tree's rule where the method is read
(`pipelex_api.method_tree_request`), so this module returns them as the archive gives them.
"""

import base64
import io
import zipfile

import pytest
from pytest_mock import MockerFixture

from pipelex_api.bundle import decode_bundle_archive
from pipelex_api.exceptions import RequestMethodError, RunnerRequestError
from tests.unit._problems import problem_of

_MAIN_MTHDS = 'domain = "b"\nmain_pipe = "echo"\n'


def _zip_b64(entries: list[tuple[str, str]]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class TestBundleArchive:
    def test_the_members_are_returned_in_archive_order_with_their_bytes(self):
        entries = decode_bundle_archive(bundle_b64=_zip_b64([("main.mthds", _MAIN_MTHDS), ("structures/models.py", "class Foo: ...\n")]))
        assert entries == [("main.mthds", _MAIN_MTHDS.encode("utf-8")), ("structures/models.py", b"class Foo: ...\n")]

    def test_a_directory_member_is_skipped(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("templates/", "")
            archive.writestr("templates/a.txt", "a")
        entries = decode_bundle_archive(bundle_b64=base64.b64encode(buffer.getvalue()).decode("ascii"))
        assert entries == [("templates/a.txt", b"a")]

    @pytest.mark.parametrize("name", ["../evil.py", "/etc/passwd", "a\\b.py"])
    def test_a_name_is_returned_as_the_archive_gives_it_for_the_tree_rule_to_judge(self, name: str):
        entries = decode_bundle_archive(bundle_b64=_zip_b64([(name, "x")]))
        assert entries == [(name, b"x")]

    def test_a_name_given_twice_is_returned_twice(self):
        with pytest.warns(UserWarning, match="Duplicate name"):
            bundle_b64 = _zip_b64([("notes.txt", "a"), ("notes.txt", "b")])
        assert decode_bundle_archive(bundle_b64=bundle_b64) == [("notes.txt", b"a"), ("notes.txt", b"b")]

    def test_an_empty_archive_is_refused(self):
        with pytest.raises(RunnerRequestError) as exc:
            decode_bundle_archive(bundle_b64=_zip_b64([]))
        problem = problem_of(exc.value)
        assert problem["status"] == 422
        assert problem["code"] == "request.invalid"
        assert problem["params"] == {"field": "bundle_b64"}

    def test_file_count_ceiling(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.bundle.MAX_BUNDLE_FILES", 2)
        with pytest.raises(RequestMethodError) as exc:
            decode_bundle_archive(bundle_b64=_zip_b64([(f"file_{index}.py", "x") for index in range(3)]))
        problem = problem_of(exc.value)
        assert problem["status"] == 422
        assert problem["code"] == "method.package_invalid"
        assert problem["params"] == {"reason": "too_many_files", "limit": 2}

    def test_zip_bomb_bounded_by_total_size(self, mocker: MockerFixture):
        # A highly compressible entry that decompresses well past the (patched) ceiling must be
        # refused by the bounded read, not silently expanded into memory.
        mocker.patch("pipelex_api.bundle.MAX_BUNDLE_TOTAL_BYTES", 1024)
        with pytest.raises(RequestMethodError) as exc:
            decode_bundle_archive(bundle_b64=_zip_b64([("bomb.txt", "A" * (1024 * 64))]))
        problem = problem_of(exc.value)
        assert problem["status"] == 422
        assert problem["code"] == "method.package_invalid"
        assert problem["params"] == {"reason": "bundle_too_large", "limit": 1024}

    def test_corrupt_zip_rejected(self):
        not_a_zip = base64.b64encode(b"this is definitely not a zip archive").decode("ascii")
        with pytest.raises(RunnerRequestError) as exc:
            decode_bundle_archive(bundle_b64=not_a_zip)
        problem = problem_of(exc.value)
        assert problem["status"] == 422
        assert problem["code"] == "request.malformed"
        assert problem["params"] == {"reason": "bad_zip"}

    def test_invalid_base64_rejected(self):
        with pytest.raises(RunnerRequestError) as exc:
            decode_bundle_archive(bundle_b64="!!! not base64 !!!")
        problem = problem_of(exc.value)
        assert problem["status"] == 422
        assert problem["code"] == "request.malformed"
        assert problem["params"] == {"reason": "bad_base64"}

    def test_oversized_base64_rejected_before_decode(self, mocker: MockerFixture):
        # The cheap length check on the still-encoded string fires before any b64decode.
        mocker.patch("pipelex_api.bundle._MAX_BUNDLE_B64_CHARS", 16)
        decode_spy = mocker.spy(base64, "b64decode")
        with pytest.raises(RunnerRequestError) as exc:
            decode_bundle_archive(bundle_b64="A" * 64)
        problem = problem_of(exc.value)
        assert problem["status"] == 413
        assert problem["code"] == "request.too_large"
        assert problem["params"] == {"limit": 16, "size": 64}
        decode_spy.assert_not_called()
