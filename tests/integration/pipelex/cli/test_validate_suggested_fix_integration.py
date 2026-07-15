"""Integration pin: human ``pipelex validate bundle`` surfaces the 💡 suggested-fix line.

Runs the real validation path (only the boot/teardown/telemetry seams are patched — the
suite's session boot owns the runtime) on a fixable bundle, and asserts the rendered output
carries the per-error ``💡 Suggested fix:`` line plus the actionable ``pipelex fix bundle``
footer, wired end-to-end through the shared items builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.validate.bundle_cmd import validate_bundle_cmd

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture

VALIDATE_CORE_MODULE = "pipelex.cli.commands.validate._validate_core"

_FIXABLE_SEQUENCE_MTHDS = """domain = "human_validate_fixable"
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


class TestValidateSuggestedFixIntegration:
    def test_fixable_bundle_renders_suggested_fix_and_actionable_footer(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        mocker.patch(f"{VALIDATE_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{VALIDATE_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{VALIDATE_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{VALIDATE_CORE_MODULE}.tag")
        recorded_console = Console(width=500, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=recorded_console)

        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            validate_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 1
        output = recorded_console.export_text()
        assert "❌ Bundle validation failed" in output
        assert "💡 Suggested fix: Set output of pipe 'list_ideas' to 'Idea[]' to match its last step" in output
        assert "can be fixed automatically" in output
        assert f"pipelex fix bundle {bundle_path}" in output
