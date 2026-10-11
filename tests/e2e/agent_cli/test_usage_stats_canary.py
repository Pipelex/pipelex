import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real CLIs for end-to-end coverage
from pathlib import Path
from typing import Any

from pipelex.system.usage_stats.usage_stats_contract import UsageStatsEnvVar
from tests.e2e.agent_cli.conftest import PIPELEX_AGENT_BIN, REPO_ROOT, write_active_routing_profile
from tests.helpers.usage_stats_capture import capture_server
from tests.helpers.usage_stats_schema import assert_envelope_is_valid
from tests.unit.pipelex.system.usage_stats.test_data import UsageStatsCanary

PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
_CANARY = UsageStatsCanary.MARKER
_TITLE = _CANARY.capitalize()

_VALID_BUNDLE = f"""\
domain = "{_CANARY}_domain"
description = "Canary {_CANARY} description"
main_pipe = "{_CANARY}_main"

[concept]
{_TITLE}Report = "Canary {_CANARY} concept"

[pipe.{_CANARY}_main]
type = "PipeSequence"
description = "Canary {_CANARY} sequence"
inputs = {{ {_CANARY}_input = "Text" }}
output = "{_TITLE}Report"
steps = [{{ pipe = "{_CANARY}_step", result = "{_CANARY}_result" }}]

[pipe.{_CANARY}_step]
type = "PipeLLM"
description = "Canary {_CANARY} step"
inputs = {{ {_CANARY}_input = "Text" }}
output = "{_TITLE}Report"
model = "claude-4.5-haiku"
prompt = "Canary {_CANARY}: ${_CANARY}_input"
"""
_INVALID_BUNDLE = _VALID_BUNDLE.replace(
    f'steps = [{{ pipe = "{_CANARY}_step", result = "{_CANARY}_result" }}]',
    f'steps = [{{ pipe = "{_CANARY}_step", result = "{_CANARY}_result" }}, {{ pipe = "{_CANARY}_missing", result = "{_CANARY}_other" }}]',
)


def _stage(*, home: Path) -> tuple[Path, Path, Path]:
    """The canary bundles, valid and invalid, each alone in a directory whose name carries the canary too."""
    valid_dir = home / f"{_CANARY}_valid_dir"
    invalid_dir = home / f"{_CANARY}_invalid_dir"
    valid_dir.mkdir()
    invalid_dir.mkdir()
    valid_bundle = valid_dir / f"{_CANARY}_bundle.mthds"
    valid_bundle.write_text(_VALID_BUNDLE, encoding="utf-8")
    invalid_bundle = invalid_dir / f"{_CANARY}_bundle.mthds"
    invalid_bundle.write_text(_INVALID_BUNDLE, encoding="utf-8")
    return valid_dir, valid_bundle, invalid_bundle


def _commands(*, home: Path) -> list[list[str]]:
    valid_dir, valid_bundle, invalid_bundle = _stage(home=home)
    output_dir = home / f"{_CANARY}_generated"
    agent = str(PIPELEX_AGENT_BIN)
    return [
        [agent, "validate", "bundle", str(valid_bundle), "--format", "json"],
        [agent, "validate", "bundle", str(invalid_bundle), "--format", "json"],
        [agent, "run", "bundle", str(valid_bundle), "--dry-run", "--mock-inputs", "--no-graph", "--format", "json"],
        [agent, "codegen", "types", str(valid_dir), "--target", "ts-zod", "--output", str(output_dir)],
        [agent, "inputs", "bundle", str(valid_bundle)],
        [str(PIPELEX_BIN), "--no-logo", "validate", "bundle", str(invalid_bundle)],
        [str(PIPELEX_BIN), "--no-logo", "codegen", "types", str(valid_dir), "--target", "python-pydantic", "--output", str(output_dir)],
    ]


def _run(*, command: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
        command, env=env, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=180
    )


def _state_text(*, home: Path) -> str:
    """Everything the shared state directory holds, names and contents."""
    state_dir = home / ".mthds" / "usage-stats"
    parts: list[str] = []
    for path in sorted(state_dir.rglob("*")):
        parts.append(path.name)
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


class TestUsageStatsCanary:
    def test_canary_never_leaves_the_machine(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        """Runs, validations and code generations on a method named everywhere with a canary print, send and keep no trace of it."""
        write_active_routing_profile(hermetic_home / ".pipelex" / "inference" / "routing_profiles.toml", "all_anthropic")
        commands = _commands(home=hermetic_home)
        stats_on_env = {name: value for name, value in offline_subprocess_env.items() if name != UsageStatsEnvVar.TOOL_SWITCH}

        printed: list[dict[str, Any]] = []
        for command in commands:
            result = _run(command=command, env={**stats_on_env, UsageStatsEnvVar.DEBUG: "1"}, cwd=hermetic_home)
            for line in result.stderr.splitlines():
                if line.startswith('{"usage_stats_debug"'):
                    printed.append(json.loads(line)["usage_stats_debug"])
        printed_names = {envelope["event"] for envelope in printed}
        assert {"command_completed", "method_validated", "run_completed", "code_generated"} <= printed_names, printed_names
        for envelope in printed:
            assert_envelope_is_valid(envelope)
        assert _CANARY not in json.dumps(printed).lower()

        with capture_server() as server:
            for command in commands:
                _run(command=command, env={**stats_on_env, UsageStatsEnvVar.ENDPOINT_OVERRIDE: server.origin, "CI": "true"}, cwd=hermetic_home)
            sent = server.events
        assert len(sent) >= len(commands)
        assert all(envelope["properties"]["ci"] is True for envelope in sent)
        assert _CANARY not in json.dumps([request.body for request in server.requests]).lower()
        assert _CANARY not in _state_text(home=hermetic_home).lower()
