"""E2E: `pipelex run` leaves the three I/O artifact files beside `graphspec.json`.

One `gha_disabled` subprocess check exercises the real binary: a dry run with graph outputs on
must leave a results directory holding `graphspec.json` and, beside it, `pipe_io_contracts.json`,
`input_form.json` and `output_form.json`, each a JSON object keyed by `pipe_ref` — the layout the
VS Code extension reads to show a data node's value.

The subprocess test inherits the ambient environment (it needs a working `.pipelex` config to
boot) and runs with `cwd` set to a tmp dir so on-disk side effects stay out of the source tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real pipelex binary for E2E coverage
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
BUNDLE_SRC = REPO_ROOT / "tests" / "data" / "input_semantics" / "probe_bundle.mthds"
COMPANION_FILE_NAMES = ("pipe_io_contracts.json", "input_form.json", "output_form.json")


class TestRunArtifactsBesideGraphspec:
    @pytest.mark.gha_disabled
    def test_dry_run_writes_the_three_siblings(self, tmp_path: Path) -> None:
        staged = tmp_path / "bundle"
        staged.mkdir()
        shutil.copy(BUNDLE_SRC, staged / BUNDLE_SRC.name)
        output_dir = tmp_path / "results"

        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [
                str(PIPELEX_BIN),
                "run",
                "pipe",
                "probe_single",
                "-L",
                str(staged),
                "--dry-run",
                "--mock-inputs",
                "--graph",
                "--no-save-working-memory",
                "--no-save-main-stuff",
                "-o",
                str(output_dir),
            ],
            cwd=str(tmp_path),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert result.returncode == 0, f"dry run must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"

        graphspecs = list(output_dir.rglob("graphspec.json"))
        assert len(graphspecs) == 1, f"expected one graphspec.json under {output_dir}, found {graphspecs}"
        results_dir = graphspecs[0].parent
        pipe_registry: dict[str, Any] = json.loads(graphspecs[0].read_text(encoding="utf-8"))["pipe_registry"]
        for file_name in COMPANION_FILE_NAMES:
            doc: dict[str, Any] = json.loads((results_dir / file_name).read_text(encoding="utf-8"))
            assert isinstance(doc, dict), f"{file_name}: an object keyed by pipe_ref"
            assert doc, f"{file_name}: at least one pipe described"
            assert set(pipe_registry) <= set(doc), f"{file_name}: every pipe the graph names is described"
