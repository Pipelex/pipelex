"""Unit tests for what a hosted run sends: the `.mthds` files a local run would load, or a name the hosted API resolves."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._hosted_sources import (
    collect_mthds_files,
    hosted_pipe_library_files,
    looks_like_method_id,
    resolve_hosted_method_target,
)
from pipelex.hosted.exceptions import HostedRunSourceError
from pipelex.system.environment import PIPELEXPATH_ENV_KEY

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

SOURCES_MODULE = "pipelex.cli.commands.run._hosted_sources"


def _write(*, path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestHostedSources:
    def test_the_primary_file_goes_first_and_each_file_once(self, tmp_path: Path) -> None:
        bundle = _write(path=tmp_path / "lib" / "bundle.mthds", content="bundle")
        _write(path=tmp_path / "lib" / "a_other.mthds", content="other")
        _write(path=tmp_path / "lib" / "nested" / "deep.mthds", content="deep")
        _write(path=tmp_path / "lib" / "notes.md", content="not a bundle")
        _write(path=tmp_path / "lib" / ".venv" / "vendored.mthds", content="excluded")
        single = _write(path=tmp_path / "single.mthds", content="single")

        files = collect_mthds_files(primary=bundle, library_dirs=[str(tmp_path / "lib"), str(single), str(tmp_path / "missing")])

        assert [mthds_file.content for mthds_file in files] == ["bundle", "other", "deep", "single"]
        assert files[0].source == str(bundle)

    def test_a_pipe_run_without_a_library_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PIPELEXPATH_ENV_KEY, raising=False)
        with pytest.raises(HostedRunSourceError, match="-L"):
            hosted_pipe_library_files(library_dirs=None)

    def test_a_pipe_run_falls_back_to_pipelexpath(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _write(path=tmp_path / "lib" / "bundle.mthds", content="bundle")
        monkeypatch.setenv(PIPELEXPATH_ENV_KEY, str(tmp_path / "lib"))

        files = hosted_pipe_library_files(library_dirs=None)

        assert [mthds_file.content for mthds_file in files] == ["bundle"]

    def test_a_library_with_no_bundle_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(HostedRunSourceError, match=r"No \.mthds file"):
            hosted_pipe_library_files(library_dirs=[str(tmp_path)])

    @pytest.mark.parametrize(
        ("target", "is_method_id"),
        [
            ("mt_abc123", True),
            ("mt_A-b_9", True),
            ("mt_", False),
            ("my-method", False),
            ("mt abc", False),
            ("github.com/Pipelex/methods/text_stats", False),
        ],
    )
    def test_a_catalog_id_is_told_from_a_method_name(self, target: str, is_method_id: bool) -> None:
        assert looks_like_method_id(target) is is_method_id

    def test_a_remote_method_with_a_local_library_is_refused(self, tmp_path: Path) -> None:
        """The hosted API resolves an address alone: it loads no library from this machine."""
        with pytest.raises(HostedRunSourceError, match="-L does not apply"):
            resolve_hosted_method_target(name="mt_abc123", pipe_override=None, library_dirs=[str(tmp_path)])

    def test_a_remote_method_is_anchored_in_the_working_directory(self) -> None:
        target = resolve_hosted_method_target(name="github.com/Pipelex/methods/text_stats@v0.1.7", pipe_override=None, library_dirs=None)

        assert target.method_ref == "github.com/Pipelex/methods/text_stats@v0.1.7"
        assert target.label == "text_stats"
        assert target.output_base_dir == Path.cwd()
        assert target.inputs_anchor_dir == Path.cwd()

    def test_a_local_method_sends_its_files_and_anchors_in_its_directory(self, mocker: MockerFixture, tmp_path: Path) -> None:
        method_dir = tmp_path / "my-method"
        _write(path=method_dir / "main.mthds", content="main")
        _write(path=tmp_path / "extra" / "extra.mthds", content="extra")
        method = mocker.MagicMock()
        method.path = method_dir
        method.provenance = None
        mocker.patch(f"{SOURCES_MODULE}.resolve_method_target", return_value=("summarize", [str(method_dir)], method))

        target = resolve_hosted_method_target(name="my-method", pipe_override=None, library_dirs=[str(tmp_path / "extra")])

        assert [mthds_file.content for mthds_file in target.mthds_files or []] == ["main", "extra"]
        assert target.pipe_code == "summarize"
        assert target.output_base_dir == method_dir
        assert target.inputs_anchor_dir == method_dir
