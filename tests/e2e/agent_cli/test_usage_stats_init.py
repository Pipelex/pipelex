import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real agent CLI for end-to-end coverage
from pathlib import Path
from typing import Any

import pytest

from pipelex.system.usage_stats.usage_stats_contract import UsageStatsEnvVar
from tests.e2e.agent_cli.conftest import PIPELEX_AGENT_BIN
from tests.helpers.usage_stats_process import make_project_dir
from tests.helpers.usage_stats_schema import assert_envelope_is_valid


def _command_completed(stderr: str) -> dict[str, Any]:
    printed: list[dict[str, Any]] = [json.loads(line)["usage_stats_debug"] for line in stderr.splitlines() if line.startswith('{"usage_stats_debug"')]
    completed = [envelope for envelope in printed if envelope["event"] == "command_completed"]
    assert len(completed) == 1, printed
    return completed[0]


class TestUsageStatsInit:
    @pytest.mark.parametrize(
        ("config", "execution", "enabled"),
        [
            ({"backends": ["anthropic", "openai"], "primary_backend": "anthropic"}, "local", {"anthropic", "openai"}),
            ({"execution": "hosted"}, "hosted", None),
        ],
    )
    def test_agent_init_reports_what_it_set(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
        config: dict[str, Any],
        execution: str,
        enabled: set[str] | None,
    ) -> None:
        """`pipelex-agent init` reports where it set runs to execute and, on this machine, the backends it enabled."""
        env = {name: value for name, value in offline_subprocess_env.items() if name != UsageStatsEnvVar.TOOL_SWITCH}
        env[UsageStatsEnvVar.DEBUG] = "1"
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
            [str(PIPELEX_AGENT_BIN), "init", "--config", json.dumps(config), "--format", "json"],
            env=env,
            cwd=str(make_project_dir(parent=hermetic_home)),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        envelope = _command_completed(result.stderr)
        assert_envelope_is_valid(envelope)
        properties = envelope["properties"]
        assert (properties["command"], properties["outcome"], properties["init_execution"]) == ("init", "succeeded", execution)
        backends = {name.removeprefix("init_backend_") for name, value in properties.items() if name.startswith("init_backend_") and value}
        if enabled is None:
            assert not [name for name in properties if name.startswith("init_backend_")]
        else:
            assert backends == enabled
