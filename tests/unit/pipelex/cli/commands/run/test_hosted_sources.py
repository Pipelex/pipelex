"""Unit tests for what a hosted run sends: the `.mthds` files a local run would load, as one tree, or a name the hosted API resolves."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._hosted_sources import (
    hosted_library_dirs,
    hosted_pipe_library_contents,
    looks_like_method_id,
    method_tree_contents,
    resolve_hosted_method_target,
)
from pipelex.hosted.exceptions import HostedRunSourceError
from pipelex.libraries.exceptions import MethodTreeLoadError
from pipelex.libraries.method_trees import list_local_method_tree
from pipelex.system.environment import PIPELEXPATH_ENV_KEY

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

SOURCES_MODULE = "pipelex.cli.commands.run._hosted_sources"


MT_REPORTS_MANIFEST = """[package]
address = "github.com/acme/reports"
version = "1.0.0"
description = "Reports"
name = "mt_reports"
main_pipe = "shout"

[exports.reports]
pipes = ["shout"]
"""
MT_REPORTS_BUNDLE = """domain = "reports"
main_pipe = "shout"

[pipe.shout]
type = "PipeLLM"
description = "Shout"
inputs = { text = "Text" }
output = "Text"
prompt = "Shout $text"
"""


def _write(*, path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestHostedSources:
    def test_the_bundle_file_goes_first_and_each_file_once_by_its_tree_path(self, tmp_path: Path) -> None:
        """The bundle's own tree sets the root: its folder's files keep their tree paths, a tree beside it goes under its name."""
        bundle = _write(path=tmp_path / "lib" / "bundle.mthds", content="bundle")
        _write(path=tmp_path / "lib" / "a_other.mthds", content="other")
        _write(path=tmp_path / "lib" / "nested" / "deep.mthds", content="deep")
        _write(path=tmp_path / "lib" / "notes.md", content="not a bundle")
        _write(path=tmp_path / "lib" / ".venv" / "vendored.mthds", content="excluded")
        # A file the library's method tree keeps out is never sent, as a local load never reads it.
        _write(path=tmp_path / "lib" / "draft.mthds", content="gitignored")
        _write(path=tmp_path / "lib" / ".gitignore", content="draft.mthds\n")
        single = _write(path=tmp_path / "single.mthds", content="single")

        contents = method_tree_contents(
            method_tree=list_local_method_tree(handed_over=bundle),
            library_dirs=[str(tmp_path / "lib"), str(single), str(tmp_path / "missing")],
        )

        assert list(contents.items()) == [
            ("bundle.mthds", b"bundle"),
            ("a_other.mthds", b"other"),
            ("nested/deep.mthds", b"deep"),
            (f"{tmp_path.name}/single.mthds", b"single"),
        ]

    def test_a_bundle_file_of_a_method_folder_is_keyed_by_its_tree_path_there(self, tmp_path: Path) -> None:
        """A bundle file under a `METHODS.toml` is a member of that method's tree, and is sent as the run names it there."""
        method_dir = tmp_path / "reports"
        _write(path=method_dir / "METHODS.toml", content=MT_REPORTS_MANIFEST)
        bundle = _write(path=method_dir / "flows" / "bundle.mthds", content=MT_REPORTS_BUNDLE)

        contents = method_tree_contents(method_tree=list_local_method_tree(handed_over=bundle), library_dirs=None)

        assert contents == {"flows/bundle.mthds": MT_REPORTS_BUNDLE.encode()}

    def test_a_tree_nested_in_the_method_s_folder_is_keyed_under_its_folder(self, tmp_path: Path) -> None:
        method_dir = tmp_path / "method"
        _write(path=method_dir / "main.mthds", content="main")
        _write(path=method_dir / "vendor" / "reports" / "METHODS.toml", content=MT_REPORTS_MANIFEST)
        _write(path=method_dir / "vendor" / "reports" / "bundle.mthds", content="reports")

        contents = method_tree_contents(method_tree=list_local_method_tree(handed_over=method_dir), library_dirs=[str(method_dir)])

        assert contents == {"main.mthds": b"main", "vendor/reports/bundle.mthds": b"reports"}

    def test_libraries_beside_the_method_are_keyed_under_their_names_each_once(self, tmp_path: Path) -> None:
        """Each goes under a top-level folder no other key uses: its name, numbered when the method or another library holds
        it, or a numbered `library-` when its name is no folder a tree may hold, so no library mixes into the method's folders.
        """
        method_dir = tmp_path / "method"
        _write(path=method_dir / "main.mthds", content="main")
        _write(path=method_dir / "shared" / "taken.mthds", content="the method's own")
        _write(path=tmp_path / "first" / "shared" / "taken.mthds", content="first taken")
        _write(path=tmp_path / "first" / "shared" / "kept.mthds", content="first kept")
        _write(path=tmp_path / "second" / "Shared" / "other.mthds", content="second")
        _write(path=tmp_path / ".hidden" / "hidden.mthds", content="hidden root")

        contents = method_tree_contents(
            method_tree=list_local_method_tree(handed_over=method_dir),
            library_dirs=[str(method_dir), str(tmp_path / "first" / "shared"), str(tmp_path / "second" / "Shared"), str(tmp_path / ".hidden")],
        )

        assert contents == {
            "main.mthds": b"main",
            "shared/taken.mthds": b"the method's own",
            "shared-2/kept.mthds": b"first kept",
            "shared-2/taken.mthds": b"first taken",
            "Shared-3/other.mthds": b"second",
            "library-1/hidden.mthds": b"hidden root",
        }

    def test_a_file_that_changed_since_its_listing_is_refused(self, mocker: MockerFixture, tmp_path: Path) -> None:
        bundle = _write(path=tmp_path / "bundle.mthds", content="bundle")
        mocker.patch(f"{SOURCES_MODULE}.read_tree_bundle_as_listed", side_effect=MethodTreeLoadError("The file changed since its listing."))

        with pytest.raises(HostedRunSourceError, match="changed since its listing"):
            method_tree_contents(method_tree=list_local_method_tree(handed_over=bundle), library_dirs=None)

    def test_a_pipe_run_without_a_library_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PIPELEXPATH_ENV_KEY, raising=False)
        with pytest.raises(HostedRunSourceError, match="-L"):
            hosted_pipe_library_contents(library_dirs=None)

    def test_a_pipe_run_falls_back_to_pipelexpath(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _write(path=tmp_path / "lib" / "bundle.mthds", content="bundle")
        monkeypatch.setenv(PIPELEXPATH_ENV_KEY, str(tmp_path / "lib"))

        contents = hosted_pipe_library_contents(library_dirs=None)

        assert contents == {"bundle.mthds": b"bundle"}

    def test_a_library_with_no_bundle_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(HostedRunSourceError, match=r"No \.mthds file"):
            hosted_pipe_library_contents(library_dirs=[str(tmp_path)])

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

        assert target.contents == {"main.mthds": b"main", "extra/extra.mthds": b"extra"}
        assert target.pipe_code == "summarize"
        assert target.output_base_dir == method_dir
        assert target.inputs_anchor_dir == method_dir

    def test_an_installed_method_named_like_a_catalog_id_is_the_installed_method(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """`mt_reports` is a valid method name: the installed method wins, as a local run would run it."""
        method_dir = tmp_path / ".mthds" / "methods" / "mt_reports"
        _write(path=method_dir / "METHODS.toml", content=MT_REPORTS_MANIFEST)
        _write(path=method_dir / "bundle.mthds", content=MT_REPORTS_BUNDLE)
        monkeypatch.chdir(tmp_path)

        target = resolve_hosted_method_target(name="mt_reports", pipe_override=None, library_dirs=None)

        assert target.method_id is None
        assert target.contents == {"bundle.mthds": MT_REPORTS_BUNDLE.encode()}
        assert target.pipe_code == "shout"

    def test_a_catalog_id_no_installed_method_bears_is_sent_as_an_id(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)

        target = resolve_hosted_method_target(name="mt_reports", pipe_override=None, library_dirs=None)

        assert target.method_id == "mt_reports"
        assert target.contents is None

    def test_the_library_of_a_run_is_its_library_dirs_else_pipelexpath(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """As a local run loads it: `-L` replaces PIPELEXPATH, and PIPELEXPATH is read only without it."""
        monkeypatch.setenv(PIPELEXPATH_ENV_KEY, str(tmp_path / "shared"))

        assert hosted_library_dirs(library_dirs=["lib"]) == ["lib"]
        assert hosted_library_dirs(library_dirs=[]) == []
        assert hosted_library_dirs(library_dirs=None) == [tmp_path / "shared"]

        monkeypatch.delenv(PIPELEXPATH_ENV_KEY)
        assert hosted_library_dirs(library_dirs=None) is None
