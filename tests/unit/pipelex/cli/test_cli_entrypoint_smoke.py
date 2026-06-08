"""Smoke test: the pipelex CLI must start under whatever typer/click is installed.

Regression guard for the "no active click context" crash. Under
typer >= 0.26 / click >= 8.4 the group callback (`app_callback`) ran without an
active *global* click context, so it raised `RuntimeError: There is no active
click context` and **every subcommand exited 1 before doing anything** — root
`--help` happened to survive, but `pipelex build --help`, `pipelex worker --help`,
etc. did not. A fresh `pip install pipelex` pulls those versions, so the shipped
CLI was broken for end users while our `uv.lock` (older typer) masked it locally.

Two things make this test catch the bug where the existing CLI tests did not:

1. It invokes the **real console-script entry point via subprocess** — not
   typer's ``CliRunner``. ``CliRunner.invoke`` pushes its own click context, so
   it would pass even when the global context is missing; only the real entry
   point reproduces the failure.
2. It uses **subcommand** ``--help``, which exercises ``app_callback`` (so it
   reproduces the crash) while needing no pipelex config or inference — keeping
   it cheap enough to run in the normal CI suite, not gated behind a marker.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 -- invokes the real pipelex binary on purpose
import sys
from pathlib import Path

import pytest

# Resolve the console script next to the running interpreter (the test venv);
# fall back to PATH. Resolving from sys.executable keeps it correct under
# tox/nox/uv venvs regardless of how PATH is set.
_CANDIDATE = Path(sys.executable).parent / "pipelex"
PIPELEX_BIN = str(_CANDIDATE) if _CANDIDATE.exists() else (shutil.which("pipelex") or str(_CANDIDATE))


class TestCliEntrypointStarts:
    """The installed `pipelex` entry point must start for every subcommand."""

    @pytest.mark.parametrize(
        "args",
        [
            ["--help"],
            ["build", "--help"],
            ["run", "--help"],
            ["validate", "--help"],
            ["init", "--help"],
            ["worker", "--help"],
        ],
    )
    def test_subcommand_starts_and_exits_zero(self, args: list[str]) -> None:
        result = subprocess.run(  # noqa: S603 -- fixed, trusted argv
            [PIPELEX_BIN, *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        combined = f"{result.stdout}\n{result.stderr}"
        assert result.returncode == 0, (
            f"`pipelex {' '.join(args)}` exited {result.returncode}; the CLI failed to start under the installed typer/click.\n{combined}"
        )
        assert "no active click context" not in combined.lower(), f"`pipelex {' '.join(args)}` hit the click-context regression.\n{combined}"
