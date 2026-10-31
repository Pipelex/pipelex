"""Which variables a `.env` loaded at import replaced, and which file holds each one's value.

These cases run in a **subprocess**: the files are loaded once, when `pipelex.system.environment` is first imported,
so only a fresh interpreter can show what an import replaced.
"""

import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap
from pathlib import Path

import pytest

from pipelex.system.environment import PIPELEX_HOME_ENV_KEY

#: Wall-clock bound on each import subprocess, so an import that hangs presents as a failure.
SUBPROCESS_TIMEOUT_SECONDS = 120

#: Imports the environment module in a fresh interpreter and reports, for each name, its value and its `.env` source.
_IMPORT_SCRIPT = textwrap.dedent(
    """
    import json
    import os
    import sys

    from pipelex.system.environment import get_dotenv_source

    print(json.dumps({
        name: {"value": os.environ.get(name), "source": str(source) if (source := get_dotenv_source(env_var=name)) else None}
        for name in sys.argv[1:]
    }))
    """
)

REPLACED_BY_HOME = "PIPELEX_DOTENV_TEST_REPLACED_BY_HOME"
REPLACED_BY_BOTH = "PIPELEX_DOTENV_TEST_REPLACED_BY_BOTH"
SET_WITHOUT_PROCESS_VALUE = "PIPELEX_DOTENV_TEST_SET_WITHOUT_PROCESS_VALUE"
SET_TO_THE_SAME_VALUE = "PIPELEX_DOTENV_TEST_SET_TO_THE_SAME_VALUE"
UNNAMED = "PIPELEX_DOTENV_TEST_UNNAMED"
NAMES = (REPLACED_BY_HOME, REPLACED_BY_BOTH, SET_WITHOUT_PROCESS_VALUE, SET_TO_THE_SAME_VALUE, UNNAMED, PIPELEX_HOME_ENV_KEY)


class TestDotenvSourcesAtImport:
    @pytest.fixture
    def report(self, tmp_path: Path) -> dict[str, dict[str, str | None]]:
        """Import pipelex with a home `.env` and a working directory's `.env` over a process environment of known values."""
        pipelex_home = tmp_path / "home" / ".pipelex"
        pipelex_home.mkdir(parents=True)
        (pipelex_home / ".env").write_text(
            f"{REPLACED_BY_HOME}=from-the-home\n{REPLACED_BY_BOTH}=from-the-home\n{PIPELEX_HOME_ENV_KEY}={tmp_path / 'elsewhere'}\n",
            encoding="utf-8",
        )
        working_dir = tmp_path / "project"
        working_dir.mkdir()
        (working_dir / ".env").write_text(
            f"{REPLACED_BY_BOTH}=from-the-project\n{SET_WITHOUT_PROCESS_VALUE}=from-the-project\n{SET_TO_THE_SAME_VALUE}=as-exported\n",
            encoding="utf-8",
        )
        env = {name: value for name, value in os.environ.items() if name not in NAMES}
        env.update(
            {
                "HOME": str(tmp_path / "home"),
                "USERPROFILE": str(tmp_path / "home"),
                PIPELEX_HOME_ENV_KEY: str(pipelex_home),
                REPLACED_BY_HOME: "as-exported",
                REPLACED_BY_BOTH: "as-exported",
                SET_TO_THE_SAME_VALUE: "as-exported",
                UNNAMED: "as-exported",
            }
        )
        try:
            result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
                [sys.executable, "-c", _IMPORT_SCRIPT, *NAMES],
                capture_output=True,
                text=True,
                check=False,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
                env=env,
                cwd=working_dir,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"importing pipelex did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s"
            raise AssertionError(msg) from exc
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        parsed: dict[str, dict[str, str | None]] = json.loads(result.stdout.strip().splitlines()[-1])
        return parsed

    def test_each_replaced_variable_names_the_file_holding_its_value(self, report: dict[str, dict[str, str | None]], tmp_path: Path) -> None:
        """The last file to name a variable holds its value; a variable the process did not hold counts as replaced."""
        home_dotenv = str((tmp_path / "home" / ".pipelex" / ".env").resolve())
        project_dotenv = str((tmp_path / "project" / ".env").resolve())

        assert report[REPLACED_BY_HOME] == {"value": "from-the-home", "source": home_dotenv}
        assert report[REPLACED_BY_BOTH] == {"value": "from-the-project", "source": project_dotenv}
        assert report[SET_WITHOUT_PROCESS_VALUE] == {"value": "from-the-project", "source": project_dotenv}

    def test_a_variable_holding_what_the_process_was_started_with_has_no_source(
        self, report: dict[str, dict[str, str | None]], tmp_path: Path
    ) -> None:
        """A `.env` setting the exported value changed nothing, no `.env` names the other, and `PIPELEX_HOME` is never moved."""
        assert report[SET_TO_THE_SAME_VALUE] == {"value": "as-exported", "source": None}
        assert report[UNNAMED] == {"value": "as-exported", "source": None}
        assert report[PIPELEX_HOME_ENV_KEY] == {"value": str(tmp_path / "home" / ".pipelex"), "source": None}
