"""After the default `pipelex init`, which sets up hosted runs, the installed `pipelex doctor` passes with a key and no provider key.

Hosted runs boot nothing on this machine, so the doctor reports the provider credentials and the local model check as
needed only for `--local` runs, and judges the setup by its Pipelex API key, which it never sends anywhere.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import] -- invokes the real pipelex binaries on purpose
from pathlib import Path

from tests.helpers.login_browser import TEST_KEY

REPO_ROOT = Path(__file__).resolve().parents[4]
VENV_BIN = REPO_ROOT / ".venv" / "bin"


def _run(*, args: list[str], env: dict[str, str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [str(VENV_BIN / "pipelex"), "--no-logo", *args],
        env=env,
        cwd=env["HOME"],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


class TestDoctorHostedSubprocess:
    def test_a_hosted_setup_passes_with_a_key_and_fails_naming_pipelex_login_without_one(self, fresh_home_env: dict[str, str]) -> None:
        init = _run(args=["init"], env=fresh_home_env, stdin="\n" * 20)
        assert init.returncode == 0, init.stdout + init.stderr

        with_key = _run(args=["doctor"], env=fresh_home_env)
        with_key_transcript = with_key.stdout + with_key.stderr
        assert with_key.returncode == 0, with_key_transcript
        assert "Manual Fixes Required" not in with_key_transcript
        assert TEST_KEY not in with_key_transcript

        without_key_env = {name: value for name, value in fresh_home_env.items() if name != "PIPELEX_API_KEY"}
        without_key = _run(args=["doctor"], env=without_key_env)
        without_key_transcript = without_key.stdout + without_key.stderr
        assert without_key.returncode == 1, without_key_transcript
        assert "pipelex login" in without_key_transcript
