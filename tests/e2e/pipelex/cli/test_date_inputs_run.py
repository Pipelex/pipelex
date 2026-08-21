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
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real pipelex binary for E2E coverage
from pathlib import Path

import pytest

from pipelex.test_extras.mthds_corpus.loader import get_entry

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
# The bundle is a corpus entry: the corpus is the single source for language-level `.mthds`
# methods. Only the bundle file is staged — the entry's manifest and canonical inputs are
# corpus metadata, and this test supplies its own `inputs.toml`.
BUNDLE_SRC = get_entry(name="native_date_departure").bundle_path

# A bare top-level TOML offset-datetime literal — the loader converts it into a native Date input.
INPUTS_TOML = "departure = 2026-07-07T15:40:00+02:00\n"


class TestDateInputsRun:
    @pytest.mark.gha_disabled
    def test_date_toml_literal_input_dry_run(self, tmp_path: Path) -> None:
        staged = tmp_path / "date_departure"
        staged.mkdir()
        shutil.copy2(BUNDLE_SRC, staged / BUNDLE_SRC.name)
        inputs_toml = staged / "inputs.toml"
        inputs_toml.write_text(INPUTS_TOML, encoding="utf-8")

        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
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
