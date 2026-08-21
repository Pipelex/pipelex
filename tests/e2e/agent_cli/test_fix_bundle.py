"""E2E tests for ``pipelex-agent fix bundle`` via subprocess."""

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - invokes the real pipelex-agent binary for E2E coverage
from typing import TYPE_CHECKING

import pytest

from tests.e2e.agent_cli.conftest import PIPELEX_AGENT_BIN, set_gateway_enabled

if TYPE_CHECKING:
    from pathlib import Path

_FIXABLE_SEQUENCE_MTHDS = """domain = "agent_fix_e2e"
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

_UNFIXABLE_MTHDS = """domain = "agent_fix_e2e_unfixable"
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
            str(PIPELEX_AGENT_BIN),
            "fix",
            "bundle",
            str(bundle_path),
            "--format",
            "json",
        ],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


@pytest.mark.gha_disabled
class TestFixBundleE2E:
    def test_fixable_bundle_outputs_clean_json_and_writes_file(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=False)
        bundle_path = hermetic_home / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        result = _run_fix_bundle(bundle_path, env=offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 0, f"fix bundle must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        payload = json.loads(result.stdout)
        assert payload["success"] is True
        assert payload["is_valid"] is True
        assert [fix["fix_code"] for fix in payload["fixes_applied"]] == ["match-sequence-output"]
        assert payload["files_written"] == [str(bundle_path.resolve())]
        assert 'output = "Idea[]"' in bundle_path.read_text(encoding="utf-8")

    def test_unfixable_bundle_outputs_json_error_and_exit_one(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=False)
        bundle_path = hermetic_home / "bundle.mthds"
        bundle_path.write_text(_UNFIXABLE_MTHDS, encoding="utf-8")

        result = _run_fix_bundle(bundle_path, env=offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 1, f"unfixable bundle must exit 1.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert result.stdout == ""
        payload = json.loads(result.stderr)
        assert payload["error_type"] == "FixBundleError"
        assert payload["is_valid"] is False
        assert payload["remaining_errors"]
