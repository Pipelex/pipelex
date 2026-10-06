"""E2E tests for offline-mode dry-run via the agent CLI subprocess.

These tests invoke the real ``pipelex-agent run bundle ... --dry-run --mock-inputs`` against
the same surface codex-sandbox handoffs use, with no network and dummy credentials. Each test
gets its own ``HOME``; the ``conftest`` fixtures handle the .pipelex/ scaffolding.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real pipelex-agent binary for E2E coverage
from typing import TYPE_CHECKING, cast

import pytest

from tests.e2e.agent_cli.conftest import (
    OFFLINE_BUNDLES_DIR,
    PIPELEX_AGENT_BIN,
    write_active_routing_profile,
)

if TYPE_CHECKING:
    from pathlib import Path


def _stage_bundle(source_bundle_dir: Path, dest_root: Path) -> Path:
    """Copy a bundle directory into ``dest_root`` so the agent CLI's on-disk side effects
    (e.g. ``dry_run.json`` written alongside the bundle) never pollute the source tree.
    """
    staged = dest_root / source_bundle_dir.name
    shutil.copytree(source_bundle_dir, staged)
    return staged


def _run_agent_bundle(bundle_dir: Path, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke ``pipelex-agent run bundle <dir> --dry-run --mock-inputs`` and capture output.

    The ``cwd`` MUST be set to the hermetic HOME so ``find_project_root`` stops walking at
    ``Path.home()`` and the subprocess uses the test's ``.pipelex/`` instead of the
    repository's project-level one. ``bundle_dir`` SHOULD be a staged copy (see
    ``_stage_bundle``) — the CLI writes ``dry_run.json`` next to the bundle file.
    """
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [
            str(PIPELEX_AGENT_BIN),
            "run",
            "bundle",
            str(bundle_dir),
            "--dry-run",
            "--mock-inputs",
            "--no-graph",
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


def _parse_agent_json(output: str) -> dict[str, object]:
    """Parse the last TOP-LEVEL JSON object in agent CLI output.

    Walks the output forward; on each successful ``raw_decode`` we advance past the entire
    decoded object so nested dicts inside an already-decoded envelope are NOT re-parsed.
    Without that skip, ``json.dumps(envelope, indent=2)`` of a nested-dict payload would
    cause the helper to return whichever inner dict ``raw_decode`` lands on last.

    Returning the last top-level dict (rather than the first) handles the case where the
    agent CLI emits a structured-log preamble before the real ``agent_success`` /
    ``agent_error`` envelope.
    """
    output = output.strip()
    if not output:
        msg = "Expected JSON output from agent CLI but got empty string"
        raise AssertionError(msg)
    decoder = json.JSONDecoder()
    last_parsed: dict[str, object] | None = None
    start = 0
    while start < len(output):
        if output[start] != "{":
            start += 1
            continue
        try:
            parsed, consumed = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            start += 1
            continue
        if isinstance(parsed, dict):
            last_parsed = cast("dict[str, object]", parsed)
        # Skip past the entire decoded value so we don't re-enter nested dicts.
        start += consumed
    if last_parsed is not None:
        return last_parsed
    msg = f"Could not find JSON object in agent output: {output!r}"
    raise AssertionError(msg)


@pytest.mark.gha_disabled  # Slow subprocess-based E2E; runs locally and on PR-gated workflows.
class TestOfflineDryRun:
    def test_parse_agent_json_returns_last_when_preamble_present(self) -> None:
        """Regression: a JSON-shaped log preamble must not shadow the real agent envelope.

        Agent CLI output sometimes begins with structured log lines before the
        ``agent_success`` / ``agent_error`` envelope. ``_parse_agent_json`` must walk past
        the preamble and return the LAST top-level decoded dict.
        """
        output = '{"level": "info", "msg": "starting"}\n{"text": "real result"}'
        parsed = _parse_agent_json(output)
        assert parsed == {"text": "real result"}, parsed

    def test_parse_agent_json_returns_envelope_not_nested_dict(self) -> None:
        """Regression: a pretty-printed envelope with nested dicts must surface the OUTER
        envelope, not the last nested object.

        ``json.dumps(payload, indent=2)`` puts every nested ``{`` on its own line. A naive
        walker would re-decode each nested dict at its own start position and overwrite
        ``last_parsed`` with the deepest one — which would silently break every assertion
        in this test class that reads envelope-level keys (``"error"``, ``"text"``, etc.).
        The helper must advance past the entire decoded value after each top-level parse.
        """
        envelope = {
            "text": "mock result",
            "warnings": [{"id": "WARN-1", "type": "SomeWarning"}],
        }
        parsed = _parse_agent_json(json.dumps(envelope, indent=2))
        assert parsed == envelope, parsed
        assert "text" in parsed, f"the outer envelope (with 'text') must be returned, not a nested dict: {parsed!r}"
        assert "warnings" in parsed, f"the outer envelope (with 'warnings') must be returned: {parsed!r}"

    def test_byok_offline_succeeds(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        """BYOK + no network → dry-run exits 0 with structured success JSON."""
        pipelex_dir = hermetic_home / ".pipelex"
        write_active_routing_profile(pipelex_dir / "inference" / "routing_profiles.toml", "all_anthropic")

        staged_bundle = _stage_bundle(OFFLINE_BUNDLES_DIR / "byok_simple", hermetic_home)
        result = _run_agent_bundle(staged_bundle, offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 0, f"BYOK dry-run must succeed offline.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        payload = _parse_agent_json(result.stdout)
        # A successful run envelope has no "error" field; the dry-run renders the pipe's
        # synthetic output under "text" (or a typed key) instead.
        assert "error" not in payload, payload
        assert "text" in payload, payload
