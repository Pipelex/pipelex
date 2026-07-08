"""Integration tests for the human ``pipelex fix bundle`` command against the real fix loop.

Mirrors ``test_agent_fix_bundle.py``: the Pipelex boot/teardown/telemetry seams are patched
(the suite's session boot owns the runtime), while ``fix_bundle_file`` runs for real against
``tmp_path`` copies — so these pin the whole command path: resolution, loop, mutation on disk,
human rendering, and exit codes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
import tomlkit
import typer
from rich.console import Console

from pipelex.cli.commands.fix.bundle_cmd import fix_bundle_cmd

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import Any

    from pytest_mock import MockerFixture

FIX_CORE_MODULE = "pipelex.cli.commands.fix._fix_core"

_FIXABLE_SEQUENCE_MTHDS = """domain = "human_fix_bundle"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

[pipe.list_ideas]
type = "PipeSequence"
description = "Sequence declaring a single output while the last step yields a list."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]
"""

_UNFIXABLE_MTHDS = """domain = "human_fix_unfixable"
main_pipe = "say_hi"

[pipe.say_hi]
type = "PipeLLM"
description = "References a missing concept."
inputs = { name = "MissingConcept" }
output = "Text"
prompt = "Say hi to $name"
"""


def _pipes(bundle_path: Path) -> dict[str, Any]:
    parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
    return cast("dict[str, Any]", parsed["pipe"])


class TestFixBundleHuman:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        """Recorded plain-text console patched into the fix core module."""
        recorded_console = Console(width=500, record=True, color_system=None)
        mocker.patch(f"{FIX_CORE_MODULE}.get_console", return_value=recorded_console)
        return recorded_console

    def _patch_setup(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{FIX_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{FIX_CORE_MODULE}.tag")

    def test_fixable_bundle_exits_zero_mutates_file_and_names_the_change(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        self._patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        fix_bundle_cmd(path=str(bundle_path))

        output = console.export_text()
        assert "✅ Bundle fixed — valid" in output
        assert "match-sequence-output" in output
        assert "Set output of pipe 'list_ideas' to 'Idea[]'" in output
        assert "Files written:" in output
        assert _pipes(bundle_path)["list_ideas"]["output"] == "Idea[]"

    def test_unfixable_bundle_exits_one_with_remaining_errors(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        self._patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_UNFIXABLE_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "❌ Bundle could not be fully fixed" in output
        assert "MissingConcept" in output

    def test_select_filter_is_honored_end_to_end(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        self._patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), select_codes_raw=["strip-namespace"])

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "❌ Bundle could not be fully fixed" in output
        assert _pipes(bundle_path)["list_ideas"]["output"] == "Idea"

    def test_diff_preview_leaves_originals_untouched_and_prints_diff(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        self._patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")
        original_bytes = bundle_path.read_bytes()

        fix_bundle_cmd(path=str(bundle_path), diff=True)

        assert bundle_path.read_bytes() == original_bytes
        output = console.export_text()
        assert "Preview (--diff): no files were written." in output
        assert f"--- {bundle_path.resolve()}" in output
        assert '+output = "Idea[]"' in output
        assert '-output = "Idea"' in output
        assert "✅ Fix preview — these fixes would make the bundle valid" in output

    def test_diff_preview_on_unfixable_bundle_exits_one_originals_untouched(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        self._patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_UNFIXABLE_MTHDS, encoding="utf-8")
        original_bytes = bundle_path.read_bytes()

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), diff=True)

        assert exc_info.value.exit_code == 1
        assert bundle_path.read_bytes() == original_bytes
        output = console.export_text()
        assert "❌ Fix preview — the bundle would still be invalid" in output

    def test_diff_preview_directory_mode_maps_paths_to_originals(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Directory mode mirrors the dir; diffs and labels must name the ORIGINAL files, untouched."""
        load_empty_library()
        self._patch_setup(mocker)
        bundle_dir = tmp_path / "pipeline_01"
        bundle_dir.mkdir()
        bundle_path = bundle_dir / "only_one.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")
        original_bytes = bundle_path.read_bytes()

        fix_bundle_cmd(path=str(bundle_dir), diff=True)

        assert bundle_path.read_bytes() == original_bytes
        output = console.export_text()
        assert f"--- {bundle_path.resolve()}" in output
        assert "pipelex-fix-preview-" not in output

    def test_directory_mode_auto_detects_and_fixes(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        self._patch_setup(mocker)
        bundle_dir = tmp_path / "pipeline_01"
        bundle_dir.mkdir()
        bundle_path = bundle_dir / "only_one.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        fix_bundle_cmd(path=str(bundle_dir))

        output = console.export_text()
        assert "✅ Bundle fixed — valid" in output
        assert _pipes(bundle_path)["list_ideas"]["output"] == "Idea[]"
