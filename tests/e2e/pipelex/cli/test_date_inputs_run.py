"""E2E test for native Date pipeline inputs via the ``pipelex run`` CLI.

One ``gha_disabled`` subprocess check exercises the real binary: a dry run fed an
``inputs.toml`` whose value is a bare TOML offset-datetime literal must load the TOML,
convert the top-level temporal literal into a ``DateContent`` (offset preserved), infer
``native.Date`` from the class name, and complete.

The subprocess test inherits the ambient environment (it needs a working ``.pipelex``
config to boot) and runs with ``cwd`` set to a tmp dir so on-disk side effects stay
out of the source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 — invokes the real pipelex binary for E2E coverage
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
BUNDLE_SRC = REPO_ROOT / "tests" / "e2e" / "pipelex" / "pipes" / "date" / "date_departure"

# A bare top-level TOML offset-datetime literal — the loader converts it into a native Date input.
INPUTS_TOML = "departure = 2026-07-07T15:40:00+02:00\n"


class TestDateInputsRun:
    @pytest.mark.gha_disabled
    def test_date_toml_literal_input_dry_run(self, tmp_path: Path) -> None:
        staged = tmp_path / "date_departure"
        shutil.copytree(BUNDLE_SRC, staged)
        inputs_toml = staged / "inputs.toml"
        inputs_toml.write_text(INPUTS_TOML, encoding="utf-8")

        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_BIN),
                "run",
                "pipe",
                "describe_departure",
                "-L",
                str(staged),
                "--inputs",
                str(inputs_toml),
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
        assert result.returncode == 0, f"Date-TOML-literal-inputs dry run must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "Loaded inputs from" in result.stdout
        assert "inputs.toml" in result.stdout
