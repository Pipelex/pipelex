"""E2E test for a native YesNo pipeline input via the ``pipelex run`` CLI.

One ``gha_disabled`` subprocess check exercises the real binary: a dry run fed an
``inputs.toml`` whose value is the envelope form for a YesNo input
(``{concept = "YesNo", content = true}``) must load the TOML, shape the bool into
``YesNoContent`` through the factory's YesNo arm, and complete.

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

from pipelex.test_extras.mthds_corpus.loader import get_entry

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
# The bundle is a corpus entry: the corpus is the single source for language-level `.mthds`
# methods. Only the bundle file is staged — the entry's manifest and canonical inputs are
# corpus metadata, and this test supplies its own `inputs.toml`.
BUNDLE_SRC = get_entry(name="native_yes_no_urgent_message").bundle_path

INPUTS_TOML = """[verdict]
concept = "YesNo"
content = true
"""


class TestYesNoInputsRun:
    @pytest.mark.gha_disabled
    def test_yes_no_envelope_input_dry_run(self, tmp_path: Path) -> None:
        staged = tmp_path / "yes_no_judgment"
        staged.mkdir()
        shutil.copy2(BUNDLE_SRC, staged / BUNDLE_SRC.name)
        inputs_toml = staged / "inputs.toml"
        inputs_toml.write_text(INPUTS_TOML, encoding="utf-8")

        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_BIN),
                "run",
                "pipe",
                "explain_verdict",
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
        assert result.returncode == 0, f"YesNo-envelope-inputs dry run must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "Loaded inputs from" in result.stdout
        assert "inputs.toml" in result.stdout
