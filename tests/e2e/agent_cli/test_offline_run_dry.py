"""E2E tests for offline-mode dry-run via the agent CLI subprocess.

These tests pin Phase 5 of the offline-mode plan: invoke the real ``pipelex-agent run
bundle ... --dry-run --mock-inputs`` against the same surface that fails today in
codex-sandbox handoffs, with the remote-config URL pointed at an unreachable address so
the network behaviour is honest (real ``httpx.ConnectError``) rather than mocked. Each
test gets its own ``HOME``; the ``conftest`` fixtures handle the .pipelex/ scaffolding.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # noqa: S404 — invokes the real pipelex-agent binary for E2E coverage
from typing import TYPE_CHECKING, cast

import pytest

from tests.e2e.agent_cli.conftest import (
    OFFLINE_BUNDLES_DIR,
    PIPELEX_AGENT_BIN,
    set_gateway_enabled,
    write_active_routing_profile,
    write_remote_config_cache,
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
    return subprocess.run(  # noqa: S603
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


# A minimal but structurally complete cached remote-config payload. ``backend_model_specs``
# must include every terminal handle referenced by the default kit deck so the gateway
# membership check passes for the "known-model" scenario.
def _comprehensive_cached_backend_model_specs() -> dict[str, object]:
    """Build a ``backend_model_specs`` payload that satisfies the default kit deck.

    The kit's ``1_llm_deck.toml`` references many concrete handles via aliases/waterfalls.
    We list them all here so the gateway-membership check in ``Pipelex.setup`` accepts the
    cache. The spec body uses ``gateway_completions`` (LLMs) / ``gateway_image`` (image-gen)
    sdks since the gateway proxies to those — values are minimal but valid against
    ``InferenceModelSpecBlueprint``.
    """
    llm_handle_template: dict[str, object] = {
        "sdk": "gateway_completions",
        "model_type": "llm",
        "inputs": ["text"],
        "outputs": ["text", "structured"],
    }
    img_gen_handle_template: dict[str, object] = {
        "sdk": "gateway_image",
        "model_type": "img_gen",
    }
    extract_handle_template: dict[str, object] = {
        "sdk": "gateway_extract",
        "model_type": "text_extractor",
    }
    search_handle_template: dict[str, object] = {
        "sdk": "gateway_search",
        "model_type": "search",
    }

    llm_handles = [
        "claude-3.7-sonnet",
        "claude-4.5-haiku",
        "claude-4.5-sonnet",
        "claude-4.6-opus",
        "claude-4.6-sonnet",
        "claude-4.7-opus",
        "claude-4.8-opus",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5.1",
        "gpt-5.2",
        "mistral-large",
    ]
    img_gen_handles = [
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-image-2",
        "nano-banana",
        "nano-banana-2",
        "nano-banana-pro",
    ]
    extract_handles = ["azure-document-intelligence", "linkup-fetch"]
    search_handles = ["linkup-standard", "linkup-deep"]

    specs: dict[str, object] = {"defaults": {"sdk": "gateway_completions"}}
    for handle in llm_handles:
        specs[handle] = dict(llm_handle_template)
    for handle in img_gen_handles:
        specs[handle] = dict(img_gen_handle_template)
    for handle in extract_handles:
        specs[handle] = dict(extract_handle_template)
    for handle in search_handles:
        specs[handle] = dict(search_handle_template)
    return specs


def _cached_remote_config_payload() -> dict[str, object]:
    return {
        "posthog": {
            "project_api_key": "test-key",
            "endpoint": "https://example.invalid",
            "is_geoip_enabled": False,
            "is_debug_enabled": False,
        },
        "backend_model_specs": _comprehensive_cached_backend_model_specs(),
        "aws_region": "us-east-1",
    }


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
            "warnings": [{"id": "WARN-1", "type": "RemoteConfigStale"}],
        }
        parsed = _parse_agent_json(json.dumps(envelope, indent=2))
        assert parsed == envelope, parsed
        assert "text" in parsed, f"the outer envelope (with 'text') must be returned, not a nested dict: {parsed!r}"
        assert "warnings" in parsed, f"the outer envelope (with 'warnings') must be returned: {parsed!r}"

    def test_byok_offline_succeeds(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        """Gateway disabled + no network + no cache → dry-run exits 0 with structured success JSON."""
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=False)
        write_active_routing_profile(pipelex_dir / "inference" / "routing_profiles.toml", "all_anthropic")

        staged_bundle = _stage_bundle(OFFLINE_BUNDLES_DIR / "byok_simple", hermetic_home)
        result = _run_agent_bundle(staged_bundle, offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 0, f"BYOK dry-run must succeed offline.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        payload = _parse_agent_json(result.stdout)
        # A successful run envelope has no "error" field; the dry-run renders the pipe's
        # synthetic output under "text" (or a typed key) instead.
        assert "error" not in payload, payload
        assert "text" in payload, payload

    def test_gateway_no_cache_no_network_fails_with_unavailable(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        """Gateway enabled + no network + no cache → ``RemoteConfigUnavailableError`` with remediation hint."""
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=True)

        staged_bundle = _stage_bundle(OFFLINE_BUNDLES_DIR / "gateway_known_model", hermetic_home)
        result = _run_agent_bundle(staged_bundle, offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode != 0, f"Gateway offline with no cache must fail.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        payload = _parse_agent_json(result.stderr or result.stdout)
        assert payload.get("error_type") == "RemoteConfigUnavailableError", payload
        message = str(payload.get("message", ""))
        assert "pipelex init" in message.lower(), f"Error must mention `pipelex init` remediation; got: {message!r}"

    def test_gateway_known_with_cache_succeeds_offline(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        """Gateway enabled + no network + primed cache → dry-run exits 0 with stale-cache warning."""
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=True)
        write_remote_config_cache(pipelex_dir, _cached_remote_config_payload())

        staged_bundle = _stage_bundle(OFFLINE_BUNDLES_DIR / "gateway_known_model", hermetic_home)
        result = _run_agent_bundle(staged_bundle, offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode == 0, f"Gateway dry-run with primed cache must succeed offline.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        payload = _parse_agent_json(result.stdout)
        assert "error" not in payload, payload
        rendered = json.dumps(payload)
        assert '"type": "RemoteConfigStale"' in rendered, (
            f"Cached-source setup must surface a RemoteConfigStale warning on the envelope; got: {payload!r}"
        )

    def test_gateway_unknown_with_cache_fails_with_clear_error(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        """Bundle pipe references a model absent from the cached gateway specs → clear error.

        The default kit deck only references "known" gateway handles, so this scenario fires
        at the pipe-operator layer (the membership check at ``ModelManager.setup`` looks at
        deck presets/choice defaults, not raw per-pipe model strings). Either way the agent
        CLI must surface a structured error with the unknown handle visible — that is the
        user-facing contract.
        """
        pipelex_dir = hermetic_home / ".pipelex"
        set_gateway_enabled(pipelex_dir / "inference" / "backends.toml", enabled=True)
        write_remote_config_cache(pipelex_dir, _cached_remote_config_payload())

        staged_bundle = _stage_bundle(OFFLINE_BUNDLES_DIR / "gateway_unknown_model", hermetic_home)
        result = _run_agent_bundle(staged_bundle, offline_subprocess_env, cwd=hermetic_home)

        assert result.returncode != 0, f"Unknown-model bundle must fail.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        payload = _parse_agent_json(result.stderr or result.stdout)
        # The unknown handle should appear somewhere visible in the JSON envelope (message
        # or a structured field). Don't pin the error_type — the failure can surface either
        # as ``GatewayUnknownModelError`` (if the deck reaches the membership check) or as
        # ``PipeOperatorModelAvailabilityError`` (raw model string in the pipe). Both carry
        # the model name; what matters is that the agent gets a clear, structured signal.
        rendered = json.dumps(payload)
        assert "gpt-future-fake-99" in rendered, f"Unknown-model error must surface the model name in the JSON envelope; got: {payload!r}"
