"""The `.env` loaded at import comes from the directory `PIPELEX_HOME` names, and no `.env` can move it.

These cases run in a **subprocess**: the file is loaded once, when `pipelex.system.environment` is
first imported, so only a fresh interpreter can show which one a process loads.
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


#: Imports the environment module in a fresh interpreter and reports what it loaded.
_IMPORT_SCRIPT = textwrap.dedent(
    """
    import json
    import os
    import sys

    from pipelex.system.configuration.config_loader import ConfigLoader
    from pipelex.system.environment import get_pipelex_home_dir

    print(json.dumps({
        "sentinels": {name: os.environ.get(name) for name in sys.argv[1:]},
        "pipelex_home_env": os.environ.get("PIPELEX_HOME"),
        "home_dir": str(get_pipelex_home_dir()),
        "global_config_dir": str(ConfigLoader().global_config_dir),
    }))
    """
)

DECOY_SENTINEL = "PIPELEX_HOME_TEST_DECOY_SENTINEL"
RELOCATED_SENTINEL = "PIPELEX_HOME_TEST_RELOCATED_SENTINEL"
PROJECT_SENTINEL = "PIPELEX_HOME_TEST_PROJECT_SENTINEL"
SENTINELS = (DECOY_SENTINEL, RELOCATED_SENTINEL, PROJECT_SENTINEL)


def _import_in_a_fresh_interpreter(*, home: Path, working_dir: Path, pipelex_home: str | None) -> dict[str, object]:
    env = {name: value for name, value in os.environ.items() if name != PIPELEX_HOME_ENV_KEY and name not in SENTINELS}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    if pipelex_home is not None:
        env[PIPELEX_HOME_ENV_KEY] = pipelex_home
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", _IMPORT_SCRIPT, *SENTINELS],
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
    report: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])
    return report


class TestTheDotenvLoadedAtImport:
    @pytest.fixture
    def homes(self, tmp_path: Path) -> tuple[Path, Path]:
        """A decoy home whose `.pipelex/.env` sets one sentinel, and a relocated home whose `.env` sets another."""
        decoy = tmp_path / "decoy-home"
        (decoy / ".pipelex").mkdir(parents=True)
        (decoy / ".pipelex" / ".env").write_text(f"{DECOY_SENTINEL}=from-the-real-home\n", encoding="utf-8")
        relocated = tmp_path / "relocated-home"
        relocated.mkdir()
        (relocated / ".env").write_text(f"{RELOCATED_SENTINEL}=from-the-relocated-home\n", encoding="utf-8")
        return decoy, relocated

    @pytest.fixture
    def empty_working_dir(self, tmp_path: Path) -> Path:
        working_dir = tmp_path / "cwd"
        working_dir.mkdir()
        return working_dir

    def test_without_the_variable_the_home_dotenv_is_loaded(self, homes: tuple[Path, Path], empty_working_dir: Path) -> None:
        """The control: the decoy really is a home whose `.env` an import loads, so its absence below means something."""
        decoy, _ = homes

        report = _import_in_a_fresh_interpreter(home=decoy, working_dir=empty_working_dir, pipelex_home=None)

        assert report["sentinels"] == {DECOY_SENTINEL: "from-the-real-home", RELOCATED_SENTINEL: None, PROJECT_SENTINEL: None}
        assert report["home_dir"] == str(decoy / ".pipelex")

    def test_the_relocated_dotenv_is_loaded_and_the_real_one_is_not(self, homes: tuple[Path, Path], empty_working_dir: Path) -> None:
        decoy, relocated = homes

        report = _import_in_a_fresh_interpreter(home=decoy, working_dir=empty_working_dir, pipelex_home=str(relocated))

        assert report["sentinels"] == {DECOY_SENTINEL: None, RELOCATED_SENTINEL: "from-the-relocated-home", PROJECT_SENTINEL: None}
        assert report["home_dir"] == str(relocated.resolve())
        assert report["global_config_dir"] == str(relocated.resolve())

    def test_a_relative_value_is_pinned_at_import(self, homes: tuple[Path, Path], tmp_path: Path) -> None:
        """Resolved once against the import's working directory and written back, so a later `chdir` or a subprocess agrees."""
        decoy, relocated = homes

        report = _import_in_a_fresh_interpreter(home=decoy, working_dir=tmp_path, pipelex_home=relocated.name)

        assert report["sentinels"] == {DECOY_SENTINEL: None, RELOCATED_SENTINEL: "from-the-relocated-home", PROJECT_SENTINEL: None}
        assert report["pipelex_home_env"] == str(relocated.resolve())

    def test_a_dotenv_file_cannot_move_the_home_directory(self, homes: tuple[Path, Path], empty_working_dir: Path, tmp_path: Path) -> None:
        """The home `.env` is found through the variable, so a `.env` that set it would split the process in two.

        Both files try here: the relocated home's `.env` and the project's. The process keeps the value it was
        started with, so the configuration is read from the same directory the `.env` came from.
        """
        decoy, relocated = homes
        elsewhere = tmp_path / "elsewhere"
        with (relocated / ".env").open("a", encoding="utf-8") as home_dotenv:
            home_dotenv.write(f"{PIPELEX_HOME_ENV_KEY}={elsewhere}\n")
        (empty_working_dir / ".env").write_text(f"{PROJECT_SENTINEL}=from-the-project\n{PIPELEX_HOME_ENV_KEY}={elsewhere}\n", encoding="utf-8")

        report = _import_in_a_fresh_interpreter(home=decoy, working_dir=empty_working_dir, pipelex_home=str(relocated))

        assert report["sentinels"] == {DECOY_SENTINEL: None, RELOCATED_SENTINEL: "from-the-relocated-home", PROJECT_SENTINEL: "from-the-project"}
        assert report["pipelex_home_env"] == str(relocated)
        assert report["global_config_dir"] == str(relocated.resolve())

    def test_a_dotenv_file_cannot_set_the_variable_when_the_process_did_not(
        self, homes: tuple[Path, Path], empty_working_dir: Path, tmp_path: Path
    ) -> None:
        decoy, _ = homes
        (empty_working_dir / ".env").write_text(f"{PIPELEX_HOME_ENV_KEY}={tmp_path / 'elsewhere'}\n", encoding="utf-8")

        report = _import_in_a_fresh_interpreter(home=decoy, working_dir=empty_working_dir, pipelex_home=None)

        assert report["pipelex_home_env"] is None
        assert report["global_config_dir"] == str(decoy / ".pipelex")
