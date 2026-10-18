"""A method's folder whose tree is refused before the boot is reported as a verdict, never as a crash.

`validate bundle` and `fix bundle` list a folder's method tree before they boot, so a tree the listing refuses, here
one holding a symbolic link, is reported while no interpreter hub exists. The report used to count the fixes it could
suggest by asking the hub for its default library directories, which crashed it with a `RuntimeError` after the panel
was printed, exiting 1 by accident. The in-process test session always holds a booted hub, so only the real console
scripts, run with no hub, reproduce what a user meets.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import] - invokes the real CLI binaries, which run with no hub before the boot
from typing import TYPE_CHECKING

import pytest

from tests.e2e.agent_cli.conftest import PIPELEX_AGENT_BIN, REPO_ROOT

if TYPE_CHECKING:
    from pathlib import Path

_PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"

_BUNDLE_MTHDS = """domain = "refused_tree"
main_pipe = "say_hello"

[pipe.say_hello]
type = "PipeLLM"
description = "Say hello"
output = "Text"
prompt = "Say hello"
"""

_LINK_NAME = "linked_notes.txt"


def _write_folder_holding_a_link(*, directory: Path) -> Path:
    method_dir = directory / "method"
    method_dir.mkdir()
    (method_dir / "bundle.mthds").write_text(_BUNDLE_MTHDS, encoding="utf-8")
    outside_file = directory / "notes.txt"
    outside_file.write_text("Notes kept outside the method.\n", encoding="utf-8")
    (method_dir / _LINK_NAME).symlink_to(outside_file)
    return method_dir


def _command_line(*, surface: str, method_dir: Path) -> list[str]:
    match surface:
        case "pipelex validate":
            return [str(_PIPELEX_BIN), "--no-logo", "validate", "bundle", str(method_dir)]
        case "pipelex fix":
            return [str(_PIPELEX_BIN), "--no-logo", "fix", "bundle", str(method_dir)]
        case "pipelex-agent validate":
            return [str(PIPELEX_AGENT_BIN), "validate", "bundle", str(method_dir)]
        case "pipelex-agent fix":
            return [str(PIPELEX_AGENT_BIN), "fix", "bundle", str(method_dir)]
        case _:
            msg = f"Unknown surface '{surface}'"
            raise ValueError(msg)


class TestRefusedTreeBeforeBoot:
    @pytest.mark.parametrize("surface", ["pipelex validate", "pipelex fix", "pipelex-agent validate", "pipelex-agent fix"])
    def test_a_folder_refused_before_the_boot_exits_1_without_a_traceback(
        self, tmp_path: Path, offline_subprocess_env: dict[str, str], surface: str
    ) -> None:
        """The refusal names the link and exits with the invalid verdict's code, 1, with no traceback behind it."""
        method_dir = _write_folder_holding_a_link(directory=tmp_path)

        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            _command_line(surface=surface, method_dir=method_dir),
            env=offline_subprocess_env,
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        output = completed.stdout + completed.stderr
        assert completed.returncode == 1, output
        assert "Traceback" not in output
        assert "RuntimeError" not in output
        assert "InterpreterHub is not initialized" not in output
        assert _LINK_NAME in output
