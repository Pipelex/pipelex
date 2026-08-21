"""E2E test for TOML pipeline inputs via the ``pipelex run`` CLI.

One ``gha_disabled`` subprocess check exercises the real binary: a dry run fed an
``inputs.toml`` (instead of ``inputs.json``) must load the TOML, resolve the relative
``url`` against the inputs file's directory, and complete. The staged bundle is the
same ``csv_demo`` fixture used by the CSV e2e tests; the test writes the TOML
equivalent of its ``inputs.json`` into the staged copy.

The subprocess test inherits the ambient environment (it needs a working ``.pipelex``
config to boot) and runs with ``cwd`` set to a tmp dir so on-disk side effects stay
out of the source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real pipelex binary for E2E coverage
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
BUNDLE_SRC = REPO_ROOT / "tests" / "integration" / "pipelex" / "csv" / "csv_demo"

INPUTS_TOML = """[people]
concept = "csv_demo.Person"

[people.content]
url = "people.csv"
"""


class TestTomlInputsRun:
    @pytest.mark.gha_disabled
    def test_toml_inputs_dry_run(self, tmp_path: Path) -> None:
        staged = tmp_path / "csv_demo"
        shutil.copytree(BUNDLE_SRC, staged)
        inputs_toml = staged / "inputs.toml"
        inputs_toml.write_text(INPUTS_TOML, encoding="utf-8")

        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [
                str(PIPELEX_BIN),
                "run",
                "pipe",
                "summarize_people",
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
        assert result.returncode == 0, f"TOML-inputs dry run must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "Loaded inputs from" in result.stdout
        assert "inputs.toml" in result.stdout
