"""E2E tests for the human ``pipelex fix bundle`` command via subprocess.

Reuses the hermetic-HOME harness of the agent-CLI E2E suite (imported fixtures) and invokes
the real ``.venv/bin/pipelex`` binary, so the whole surface is exercised: Typer registration,
boot, the fix loop, human rendering, and exit codes.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import] - invokes the real pipelex binary for E2E coverage
from typing import TYPE_CHECKING

import pytest

from tests.e2e.agent_cli.conftest import REPO_ROOT, set_gateway_enabled

if TYPE_CHECKING:
    from pathlib import Path

PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"

_FIXABLE_SEQUENCE_MTHDS = """domain = "human_fix_e2e"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

[pipe.list_ideas]
type = "PipeSequence"
description = "Sequence declaring a single output while the last step yields a list."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]
"""

_UNFIXABLE_MTHDS = """domain = "human_fix_e2e_unfixable"
main_pipe = "say_hi"

[pipe.say_hi]
type = "PipeLLM"
description = "References a missing concept."
inputs = { name = "MissingConcept" }
output = "Text"
prompt = "Say hi to $name"
"""


def _run_fix_bundle(bundle_path: Path, *, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [
            str(PIPELEX_BIN),
            "--no-logo",
            "fix",
            "bundle",
            str(bundle_path),
        ],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


@pytest.mark.gha_disabled
class TestFixBundleHumanE2E:
    def test_fixable_bundle_exits_zero_names_change_and_writes_file(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=False)
        bundle_path = hermetic_home / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        result = _run_fix_bundle(bundle_path, env=offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 0, f"fix bundle must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "Bundle fixed" in result.stdout
        assert "match-sequence-output" in result.stdout
        assert 'output = "Idea[]"' in bundle_path.read_text(encoding="utf-8")

    def test_unfixable_bundle_exits_one_with_remaining_errors(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=False)
        bundle_path = hermetic_home / "bundle.mthds"
        bundle_path.write_text(_UNFIXABLE_MTHDS, encoding="utf-8")

        result = _run_fix_bundle(bundle_path, env=offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 1, f"unfixable bundle must exit 1.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "could not be fully fixed" in result.stdout
        assert "MissingConcept" in result.stdout
