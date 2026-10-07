"""The installed `pipelex init` and `pipelex-agent init` take the hosted path end to end, with no login wait when a key is set.

A machine or a test harness that sets `PIPELEX_API_KEY` and presses Enter at every prompt must see `pipelex init` exit,
not wait for a browser: Enter takes the hosted Pipelex API, and the key already set is kept without a login.
"""

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- invokes the real pipelex binaries on purpose
from pathlib import Path

from pipelex.cli.commands.init.setup_path import read_run_execution
from pipelex.hosted.run_config import RunExecution
from tests.helpers.login_browser import TEST_KEY

REPO_ROOT = Path(__file__).resolve().parents[4]
VENV_BIN = REPO_ROOT / ".venv" / "bin"


class TestInitHostedSubprocess:
    def test_pipelex_init_with_a_key_set_takes_the_hosted_default_and_exits(self, fresh_home_env: dict[str, str]) -> None:
        home = Path(fresh_home_env["HOME"])
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [str(VENV_BIN / "pipelex"), "--no-logo", "init"],
            env=fresh_home_env,
            cwd=str(home),
            input="\n" * 20,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        pipelex_dir = home / ".pipelex"
        assert read_run_execution(pipelex_toml_path=pipelex_dir / "pipelex.toml") == RunExecution.HOSTED
        assert (pipelex_dir / "inference" / "backends.toml").is_file()
        assert (pipelex_dir / "telemetry.toml").is_file()
        # The prompts go to stdout and everything the console prints to stderr
        transcript = result.stdout + result.stderr
        assert "Where should your runs execute?" in transcript
        assert "already set" in transcript
        assert TEST_KEY not in transcript
        assert not (pipelex_dir / ".env").exists()

    def test_pipelex_agent_init_hosted_reports_the_execution(self, fresh_home_env: dict[str, str]) -> None:
        home = Path(fresh_home_env["HOME"])
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [str(VENV_BIN / "pipelex-agent"), "init", "--global", "--config", '{"execution": "hosted"}', "--format", "json"],
            env=fresh_home_env,
            cwd=str(home),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["execution"] == "hosted"
        assert payload["api_key_set"] is True
        assert read_run_execution(pipelex_toml_path=home / ".pipelex" / "pipelex.toml") == RunExecution.HOSTED

    def test_pipelex_login_help_exits_0(self, fresh_home_env: dict[str, str]) -> None:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [str(VENV_BIN / "pipelex"), "--no-logo", "login", "--help"],
            env=fresh_home_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "--paste" in result.stdout
