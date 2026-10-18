"""Unit tests for resolve_bundle_target: shared path resolution for the agent CLI's validate and fix bundle commands.

Pins that ``~`` is expanded for both the ``path`` argument and each ``--library-dir`` entry, and that a folder is read
whole, as its method tree, whatever its bundles declare of where the method starts.
"""

import json
from pathlib import Path

import pytest
import typer

from pipelex.cli.agent_cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.pipeline.exceptions import ValidateBundleError
from tests.helpers.method_folders import MethodFolderShape, write_method_folder


class TestResolveBundleTarget:
    def test_file_mode_expands_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A ``~/foo.mthds`` file argument resolves to its absolute path, never the literal ``~`` form."""
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "foo.mthds"
        bundle_file.write_text('domain = "x"\n', encoding="utf-8")

        target = resolve_bundle_target("~/foo.mthds", library_dir=None)

        assert target.bundle_path == bundle_file
        assert target.method_dir is None
        assert target.method_tree is None
        assert target.library_dirs is None

    def test_directory_mode_expands_tilde_and_injects_expanded_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A ``~/pkg`` folder resolves to the folder itself, judged whole, and its expanded path joins the library."""
        monkeypatch.setenv("HOME", str(tmp_path))
        pkg_dir = write_method_folder(directory=tmp_path / "pkg", shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)

        target = resolve_bundle_target("~/pkg", library_dir=None)

        assert target.bundle_path is None
        assert target.method_dir == pkg_dir
        assert target.library_dirs == [pkg_dir]

    def test_library_dir_entries_expand_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A home-relative ``--library-dir`` entry is expanded to its absolute path in the returned list."""
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "foo.mthds"
        bundle_file.write_text('domain = "x"\n', encoding="utf-8")

        target = resolve_bundle_target("~/foo.mthds", library_dir=["~/mylibs"])

        assert target.library_dirs == [tmp_path / "mylibs"]

    @pytest.mark.parametrize("shape", list(MethodFolderShape))
    def test_a_folder_is_read_whole_whatever_its_main_pipes(self, tmp_path: Path, shape: MethodFolderShape) -> None:
        """No pipe to start at is needed: several main pipes, or none, are no refusal, since every bundle is judged."""
        write_method_folder(directory=tmp_path, shape=shape)

        target = resolve_bundle_target(str(tmp_path), library_dir=None)

        assert target.bundle_path is None
        assert target.method_dir == tmp_path
        assert target.method_tree is not None
        assert sorted(target.method_tree.tree_paths) == sorted(shape.files)

    @pytest.mark.parametrize("files", [{}, {".DS_Store": "", "notes.md": "# Notes\n"}], ids=["empty", "no_bundle"])
    def test_a_folder_holding_no_bundle_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]) -> None:
        for name, content in files.items():
            (tmp_path / name).write_text(content, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path), library_dir=None)

        assert exc_info.value.exit_code == 2
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "method.invalid"
        assert problem["diagnostics"]["error_class"] == "EmptyMethodTreeError"
        assert problem["message"] == f"The folder '{tmp_path}' holds no .mthds bundle."

    def test_a_folder_whose_tree_is_refused_raises_the_verdict_for_the_command(self, tmp_path: Path) -> None:
        """A symbolic link in the tree is the invalid verdict, which each command renders as its surface does."""
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)
        outside_bundle = tmp_path.parent / f"{tmp_path.name}-outside.mthds"
        outside_bundle.write_text('domain = "outside"\n', encoding="utf-8")
        (tmp_path / "linked.mthds").symlink_to(outside_bundle)

        with pytest.raises(ValidateBundleError, match=r"linked\.mthds"):
            resolve_bundle_target(str(tmp_path), library_dir=None)

    def test_a_path_that_is_no_bundle_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path / "nope.txt"), library_dir=None)

        assert exc_info.value.exit_code == 2
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "client.argument_invalid"
        assert problem["params"] == {"argument": str(tmp_path / "nope.txt"), "reason": "not a .mthds file or a directory"}
        assert "is not a .mthds file or directory" in problem["message"]
