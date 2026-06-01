"""E2E + wiring tests for ``--save-csv`` and CSV input via the ``pipelex run`` CLI (Phase 1 — RED).

Two cheap, no-subprocess wiring checks pin that the run subcommands declare ``--save-csv``
and forward it to ``execute_run``. Two ``gha_disabled`` subprocess checks exercise the real
binary: a happy ``--save-csv`` dry-run that must drop ``summaries.csv`` at the literal cwd
path (CQ1), and a missing-input-``.csv`` run that must fail cleanly (A2 — typed error naming
the file, no Python traceback).

The subprocess tests inherit the ambient environment (they need a working ``.pipelex``
config to boot) and run with ``cwd`` set to a tmp dir so ``--save-csv summaries.csv`` and any
on-disk side effects stay out of the source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 — invokes the real pipelex binary for E2E coverage
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
BUNDLE_SRC = REPO_ROOT / "tests" / "integration" / "pipelex" / "csv" / "csv_demo"


def _stage_bundle(dest_root: Path) -> Path:
    """Copy the csv_demo bundle into ``dest_root`` so CLI side effects don't touch the source tree."""
    staged = dest_root / "csv_demo"
    shutil.copytree(BUNDLE_SRC, staged)
    return staged


class TestCsvRun:
    # ----------------------------------------------------------------------------------
    # Cheap wiring checks (no subprocess) — T2
    # ----------------------------------------------------------------------------------

    @pytest.mark.parametrize("command", [run_pipe_cmd, run_bundle_cmd, run_method_cmd])
    def test_run_command_declares_save_csv(self, command: Callable[..., None]) -> None:
        assert "save_csv" in signature(command).parameters, f"{command.__name__} must declare a --save-csv option"

    def test_bundle_cmd_forwards_save_csv(self, mocker: MockerFixture) -> None:
        mock_execute = mocker.patch("pipelex.cli.commands.run.bundle_cmd.execute_run")
        # Build the kwargs dynamically so this stays type-clean before `save_csv` exists
        # (Phase 4 adds it); the RED failure is a runtime TypeError, not a type-check error.
        call_kwargs: dict[str, object] = {"path": str(BUNDLE_SRC), "save_csv": "out.csv", "dry_run": True}
        run_bundle_cmd(**call_kwargs)  # type: ignore[arg-type]
        assert mock_execute.call_args is not None
        assert mock_execute.call_args.kwargs.get("save_csv") == "out.csv"

    # ----------------------------------------------------------------------------------
    # Subprocess E2E — gha_disabled (slow; needs a working .pipelex config)
    # ----------------------------------------------------------------------------------

    @pytest.mark.gha_disabled
    def test_save_csv_writes_file_at_literal_path(self, tmp_path: Path) -> None:
        staged = _stage_bundle(tmp_path)
        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_BIN),
                "run",
                "pipe",
                "summarize_people",
                "-L",
                str(staged),
                "--inputs",
                str(staged / "inputs.json"),
                "--save-csv",
                "summaries.csv",
                "--dry-run",
                "--no-save-working-memory",
                "--no-save-main-stuff",
                "--no-graph",
            ],
            cwd=str(tmp_path),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert result.returncode == 0, f"run must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"

        out_csv = tmp_path / "summaries.csv"
        assert out_csv.exists(), f"--save-csv must write summaries.csv at the literal cwd path; cwd contents: {list(tmp_path.iterdir())}"
        lines = out_csv.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "name,country,summary"
        assert len(lines) == 4  # header + one row per input person

    @pytest.mark.gha_disabled
    def test_missing_csv_input_fails_cleanly(self, tmp_path: Path) -> None:
        staged = _stage_bundle(tmp_path)
        (staged / "inputs_missing.json").write_text(
            '{ "people": { "concept": "csv_demo.Person", "content": { "url": "nope.csv" } } }',
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_BIN),
                "run",
                "pipe",
                "summarize_people",
                "-L",
                str(staged),
                "--inputs",
                str(staged / "inputs_missing.json"),
                "--dry-run",
                "--no-save-working-memory",
                "--no-save-main-stuff",
                "--no-graph",
            ],
            cwd=str(tmp_path),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"a missing input .csv must fail.\n{combined!r}"
        assert "Traceback (most recent call last)" not in combined, f"error must be clean, not a raw traceback: {combined!r}"
        assert "nope.csv" in combined, f"the error should name the offending CSV file: {combined!r}"
