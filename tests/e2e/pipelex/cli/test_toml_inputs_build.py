"""E2E test for TOML inputs-template generation via the ``pipelex build inputs`` CLI.

Two ``gha_disabled`` subprocess checks exercise the real binary end to end. ``build inputs bundle
--format toml`` writes an ``inputs.toml`` next to the bundle (the TOML default filename), and that
generated template must feed a ``run --dry-run`` straight back — the full generate→load round trip
across both CLI surfaces:

- **Default (light, D11).** The template is the light signature-driven shape — bare values, a
  ``# concept: ...`` comment per key, structured values as inline tables — and it dry-runs.
- **``--explicit``.** The ceremonial ``{concept, content}`` envelope form is restored (all-tables
  layout), and it dry-runs too.

The staged bundle is the same ``csv_demo`` fixture used by the CSV e2e tests; its ``inputs.json`` is
removed from the staged copy so the follow-up run cannot fall back to the JSON twin.

The subprocess calls inherit the ambient environment (they need a working ``.pipelex`` config to
boot) and run with ``cwd`` set to a tmp dir so on-disk side effects stay out of the source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 — invokes the real pipelex binary for E2E coverage
from pathlib import Path
from typing import Any, cast

import pytest
import tomli

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
BUNDLE_SRC = REPO_ROOT / "tests" / "integration" / "pipelex" / "csv" / "csv_demo"


class TestTomlInputsBuild:
    def _stage(self, tmp_path: Path) -> Path:
        """Copy the csv_demo bundle to a tmp dir and drop its inputs.json (no JSON fallback)."""
        staged = tmp_path / "csv_demo"
        shutil.copytree(BUNDLE_SRC, staged)
        (staged / "inputs.json").unlink()
        return staged

    def _build(self, staged: Path, tmp_path: Path, *, extra_args: list[str]) -> None:
        """Run ``build inputs bundle --format toml`` (plus extra args) on the staged bundle."""
        build_result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_BIN),
                "build",
                "inputs",
                "bundle",
                str(staged / "csv_demo.mthds"),
                "--pipe",
                "summarize_people",
                "--format",
                "toml",
                *extra_args,
            ],
            cwd=str(tmp_path),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert build_result.returncode == 0, f"TOML template generation must succeed.\nstdout={build_result.stdout!r}\nstderr={build_result.stderr!r}"

    def _dry_run(self, staged: Path, tmp_path: Path, inputs_toml: Path) -> None:
        """Feed the generated inputs.toml straight into ``run --dry-run`` — the round trip."""
        run_result = subprocess.run(  # noqa: S603
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
        assert run_result.returncode == 0, (
            f"Dry run fed the generated inputs.toml must succeed.\nstdout={run_result.stdout!r}\nstderr={run_result.stderr!r}"
        )
        assert "inputs.toml" in run_result.stdout

    @pytest.mark.gha_disabled
    def test_build_inputs_toml_light_default_then_dry_run(self, tmp_path: Path) -> None:
        """The default TOML template is the light shape (bare values + concept comment) and it dry-runs."""
        staged = self._stage(tmp_path)
        self._build(staged, tmp_path, extra_args=[])

        inputs_toml = staged / "inputs.toml"
        assert inputs_toml.is_file(), "The TOML default filename must be inputs.toml next to the bundle"
        raw = inputs_toml.read_text(encoding="utf-8")
        assert "# concept: csv_demo.Person[]" in raw, "Light TOML must carry the declared concept as a comment"

        template = tomli.loads(raw)
        person_items = template["people"]
        assert isinstance(person_items, list), "Person[] light form must be a bare list of person dicts"
        first_person = cast("dict[str, Any]", person_items[0])
        assert "concept" not in first_person, "The light form must not carry the envelope 'concept' key"
        assert {"name", "job", "country", "birth_year"} <= set(first_person.keys())

        self._dry_run(staged, tmp_path, inputs_toml)

    @pytest.mark.gha_disabled
    def test_build_inputs_toml_explicit_then_dry_run(self, tmp_path: Path) -> None:
        """--explicit restores the ceremonial envelope template, and it dry-runs too."""
        staged = self._stage(tmp_path)
        self._build(staged, tmp_path, extra_args=["--explicit"])

        inputs_toml = staged / "inputs.toml"
        assert inputs_toml.is_file()
        template = tomli.loads(inputs_toml.read_text(encoding="utf-8"))
        assert template["people"]["concept"] == "csv_demo.Person"
        person_items = template["people"]["content"]
        assert isinstance(person_items, list), "Person[] multiplicity must wrap content in a list"
        first_person = cast("dict[str, Any]", person_items[0])
        assert {"name", "job", "country", "birth_year"} <= set(first_person.keys())

        self._dry_run(staged, tmp_path, inputs_toml)
