"""Unit tests for resolve_bundle_target: shared path→bundle resolution for agent CLI bundle commands.

Pins that ``~`` is expanded for both the ``path`` argument and each ``--library-dir`` entry, so
home-relative inputs resolve like every other CLI path argument instead of being treated as literal
filenames/directories.
"""

from pathlib import Path

import pytest
import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.bundle_path_resolver import resolve_bundle_target


class TestResolveBundleTarget:
    def test_file_mode_expands_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A ``~/foo.mthds`` file argument resolves to its absolute path, never the literal ``~`` form."""
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "foo.mthds"
        bundle_file.write_text('domain = "x"\n', encoding="utf-8")

        bundle_path, library_dir = resolve_bundle_target("~/foo.mthds", library_dir=None)

        assert bundle_path == str(bundle_file)
        assert "~" not in bundle_path
        assert library_dir is None

    def test_directory_mode_expands_tilde_and_injects_expanded_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A ``~/pkg`` directory argument resolves its default bundle and injects the expanded dir into library_dir."""
        monkeypatch.setenv("HOME", str(tmp_path))
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        bundle_file = pkg_dir / DEFAULT_BUNDLE_FILE_NAME
        bundle_file.write_text('domain = "x"\n', encoding="utf-8")

        bundle_path, library_dir = resolve_bundle_target("~/pkg", library_dir=None)

        assert bundle_path == str(bundle_file)
        assert library_dir == [str(pkg_dir)]

    def test_library_dir_entries_expand_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A home-relative ``--library-dir`` entry is expanded to its absolute path in the returned list."""
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "foo.mthds"
        bundle_file.write_text('domain = "x"\n', encoding="utf-8")

        _, library_dir = resolve_bundle_target("~/foo.mthds", library_dir=["~/mylibs"])

        assert library_dir == [str(tmp_path / "mylibs")]

    def test_ambiguous_directory_error_names_candidates_in_sorted_order(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Ambiguous-directory diagnostics are stable across filesystem iteration order."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        try:
            (tmp_path / "b.mthds").write_text('domain = "b"\n', encoding="utf-8")
            (tmp_path / "a.mthds").write_text('domain = "a"\n', encoding="utf-8")

            with pytest.raises(typer.Exit) as exc_info:
                resolve_bundle_target(str(tmp_path), library_dir=None)
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "(a.mthds, b.mthds)" in err

    def test_directory_refuses_auto_detected_symlink(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Directory mode must not turn an external symlink target into an implicitly writable entry file."""
        outside_bundle = tmp_path.parent / f"{tmp_path.name}-outside.mthds"
        outside_bundle.write_text('domain = "outside"\n', encoding="utf-8")
        (tmp_path / DEFAULT_BUNDLE_FILE_NAME).symlink_to(outside_bundle)

        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        try:
            with pytest.raises(typer.Exit) as exc_info:
                resolve_bundle_target(str(tmp_path), library_dir=None)
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 2
        assert "Refusing to auto-detect symlinked bundle" in capsys.readouterr().err
