"""Unit tests for `api.bundle` — method-bundle materialization and its ingest guards.

Covers both transport forms (`bundle_b64` zip and the `files` map), their
equivalence, and every guard: both-forms/empty rejection, path traversal
(absolute / `..` / backslash), the file-count and total-size ceilings, the
zip-bomb bounded-decompression guard, corrupt-zip and invalid-base64 handling,
and the guaranteed temp-dir cleanup on context exit.
"""

import base64
import io
import zipfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from api.bundle import materialized_bundle, parse_bundle
from api.errors import ApiError

_MAIN_MTHDS = """\
domain = "b"
main_pipe = "echo"

[pipe.echo]
type = "PipeFunc"
description = "e"
inputs = { text = "Text" }
output = "Text"
function_name = "echo"
"""
_PIPE_FUNC_PY = "def echo(working_memory):\n    return 'hi'\n"


def _zip_b64(files: dict[str, str]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class TestBundleMaterialize:
    def test_files_map_materializes_to_disk(self):
        files = {"main.mthds": _MAIN_MTHDS, "pipe_func.py": _PIPE_FUNC_PY}
        with materialized_bundle(bundle_b64=None, files=files) as bundle:
            assert bundle.directory.is_dir()
            assert bundle.has_python_sources is True
            assert set(bundle.relpaths) == {"main.mthds", "pipe_func.py"}
            assert (bundle.directory / "main.mthds").read_text() == _MAIN_MTHDS
            assert (bundle.directory / "pipe_func.py").read_text() == _PIPE_FUNC_PY

    def test_zip_equivalent_to_files_map(self):
        files = {"main.mthds": _MAIN_MTHDS, "structures/models.py": "class Foo: ...\n"}
        with materialized_bundle(bundle_b64=None, files=files) as from_files:
            files_listing = {relpath: (from_files.directory / relpath).read_text() for relpath in from_files.relpaths}
        with materialized_bundle(bundle_b64=_zip_b64(files), files=None) as from_zip:
            zip_listing = {relpath: (from_zip.directory / relpath).read_text() for relpath in from_zip.relpaths}
        assert files_listing == zip_listing == files

    def test_nested_subdir_materializes(self):
        files = {"main.mthds": _MAIN_MTHDS, "structures/models.py": "class Foo: ...\n"}
        with materialized_bundle(bundle_b64=None, files=files) as bundle:
            nested = bundle.directory / "structures" / "models.py"
            assert nested.is_file()
            assert "structures/models.py" in bundle.relpaths

    def test_no_python_sources_flag_when_only_mthds(self):
        with materialized_bundle(bundle_b64=None, files={"main.mthds": _MAIN_MTHDS}) as bundle:
            assert bundle.has_python_sources is False

    def test_directory_cleaned_up_on_exit(self):
        with materialized_bundle(bundle_b64=None, files={"main.mthds": _MAIN_MTHDS}) as bundle:
            directory = bundle.directory
            assert directory.exists()
        assert not directory.exists()

    def test_directory_cleaned_up_on_error(self):
        captured: dict[str, object] = {}

        class _Boom(RuntimeError):
            pass

        def _run() -> None:
            with materialized_bundle(bundle_b64=None, files={"main.mthds": _MAIN_MTHDS}) as bundle:
                captured["dir"] = bundle.directory
                raise _Boom

        with pytest.raises(_Boom):
            _run()
        directory = captured["dir"]
        assert isinstance(directory, Path)
        assert not directory.exists()

    def test_both_forms_rejected(self):
        with (
            pytest.raises(ApiError) as exc,
            materialized_bundle(bundle_b64=_zip_b64({"main.mthds": _MAIN_MTHDS}), files={"main.mthds": _MAIN_MTHDS}),
        ):
            pass
        assert exc.value.status_code == 422
        assert exc.value.document["error_type"] == "InvalidBundle"

    def test_neither_form_rejected(self):
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=None, files=None):
            pass
        assert exc.value.status_code == 422
        assert exc.value.document["error_type"] == "InvalidBundle"

    def test_empty_files_rejected(self):
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=None, files={}):
            pass
        assert exc.value.status_code == 422
        assert exc.value.document["error_type"] == "InvalidBundle"

    @pytest.mark.parametrize("bad_name", ["/etc/passwd", "../evil.py", "sub/../../evil.py", "a\\b.py", "C:passwd"])
    def test_unsafe_entry_names_rejected(self, bad_name: str):
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=None, files={bad_name: "x"}):
            pass
        assert exc.value.status_code == 422
        assert exc.value.document["error_type"] == "InvalidBundle"

    def test_unsafe_entry_names_rejected_in_zip(self):
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=_zip_b64({"../evil.py": "x"}), files=None):
            pass
        assert exc.value.status_code == 422
        assert exc.value.document["error_type"] == "InvalidBundle"

    def test_file_count_ceiling(self, mocker: MockerFixture):
        mocker.patch("api.bundle.MAX_BUNDLE_FILES", 2)
        files = {f"file_{index}.py": "x" for index in range(3)}
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=None, files=files):
            pass
        assert exc.value.status_code == 413
        assert exc.value.document["error_type"] == "PayloadTooLarge"

    def test_total_size_ceiling_files(self, mocker: MockerFixture):
        mocker.patch("api.bundle.MAX_BUNDLE_TOTAL_BYTES", 64)
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=None, files={"big.py": "x" * 128}):
            pass
        assert exc.value.status_code == 413
        assert exc.value.document["error_type"] == "PayloadTooLarge"

    def test_zip_bomb_bounded_by_total_size(self, mocker: MockerFixture):
        # A highly compressible entry that decompresses well past the (patched) ceiling must be
        # refused by the bounded read, not silently expanded into memory.
        mocker.patch("api.bundle.MAX_BUNDLE_TOTAL_BYTES", 1024)
        bomb = _zip_b64({"bomb.txt": "A" * (1024 * 64)})
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=bomb, files=None):
            pass
        assert exc.value.status_code == 413
        assert exc.value.document["error_type"] == "PayloadTooLarge"

    def test_corrupt_zip_rejected(self):
        not_a_zip = base64.b64encode(b"this is definitely not a zip archive").decode("ascii")
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64=not_a_zip, files=None):
            pass
        assert exc.value.status_code == 422
        assert exc.value.document["error_type"] == "InvalidBundle"

    def test_invalid_base64_rejected(self):
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64="!!! not base64 !!!", files=None):
            pass
        assert exc.value.status_code == 400
        assert exc.value.document["error_type"] == "InvalidBase64"

    def test_parse_reports_python_sources_without_writing(self):
        # parse_bundle decodes + guards in memory only; nothing is written to disk yet.
        with_py = parse_bundle(bundle_b64=None, files={"main.mthds": _MAIN_MTHDS, "pipe_func.py": _PIPE_FUNC_PY})
        assert with_py.has_python_sources is True
        without_py = parse_bundle(bundle_b64=None, files={"main.mthds": _MAIN_MTHDS})
        assert without_py.has_python_sources is False

    def test_oversized_base64_rejected_before_decode(self, mocker: MockerFixture):
        # The cheap length check on the still-encoded string fires before any b64decode.
        mocker.patch("api.bundle._MAX_BUNDLE_B64_CHARS", 16)
        decode_spy = mocker.spy(base64, "b64decode")
        with pytest.raises(ApiError) as exc, materialized_bundle(bundle_b64="A" * 64, files=None):
            pass
        assert exc.value.status_code == 413
        assert exc.value.document["error_type"] == "PayloadTooLarge"
        decode_spy.assert_not_called()
