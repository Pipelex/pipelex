"""Smoke test: the pipelex CLI must start under whatever typer/click is installed.

Regression guard for the "no active click context" crash. Under
typer >= 0.26 / click >= 8.4 the group callback (`app_callback`) ran without an
active *global* click context, so it raised `RuntimeError: There is no active
click context` and **every subcommand exited 1 before doing anything** — root
`--help` happened to survive, but `pipelex build --help`, `pipelex validate --help`,
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
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- invokes the real pipelex binary on purpose
import sys
from pathlib import Path

import pytest


def _resolve_pipelex_bin() -> str | None:
    """Locate the installed `pipelex` console script.

    Prefer the one next to the running interpreter (the test venv) so it's correct
    under tox/nox/uv venvs regardless of PATH; fall back to PATH. Returns None when
    not found, so the test can fail with a clear message instead of letting
    subprocess raise FileNotFoundError.
    """
    bin_dir = Path(sys.executable).parent
    for name in ("pipelex", "pipelex.exe"):  # .exe covers Windows venvs
        candidate = bin_dir / name
        if candidate.exists():
            return str(candidate)
    return shutil.which("pipelex")  # PATH fallback (resolves .exe via PATHEXT on Windows)


PIPELEX_BIN = _resolve_pipelex_bin()


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
        ],
    )
    def test_subcommand_starts_and_exits_zero(self, args: list[str]) -> None:
        bin_path = PIPELEX_BIN
        if bin_path is None:
            pytest.fail("`pipelex` console script not found next to the interpreter or on PATH; install the package before running this test.")
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed, trusted argv
            [bin_path, *args],
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
