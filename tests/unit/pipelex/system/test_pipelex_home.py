"""`PIPELEX_HOME` relocates the home configuration directory, everywhere it is read.

The home directory is `~/.pipelex` unless `PIPELEX_HOME` names another one. One resolver,
`get_pipelex_home_dir`, answers for the whole package: the `.env` that `pipelex.system.environment`
loads at import asks it, and so does `ConfigLoader.global_config_dir`, through which every other
reader goes (the configuration layers, the inference files and their overrides, the first-boot copy
of the kit, `existing_config_dirs` and so `pipelex migrate`).

Every case here sets `HOME` to a decoy directory holding a `.pipelex/` of its own, so that "nothing
under the real home is read" is a claim about a directory the test controls rather than about the
developer's machine.

The `.env` cases run in a **subprocess**: the file is loaded once, when `pipelex.system.environment`
is first imported, so only a fresh interpreter can show which one a process loads.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap
from pathlib import Path

import pytest
from rich.console import Console

from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY, get_pipelex_home_dir

#: Wall-clock bound on each import subprocess, so an import that hangs presents as a failure.
SUBPROCESS_TIMEOUT_SECONDS = 120

#: The one function allowed to join the user's home directory with `.pipelex`.
RESOLVER_SITE = ("pipelex/system/environment.py", "get_pipelex_home_dir")

REPO_ROOT = Path(__file__).resolve().parents[4]

#: The source trees the guard sweeps: the library and the API server member.
SWEPT_SOURCE_ROOTS = ("pipelex", "api/pipelex_api")


@pytest.fixture
def decoy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory whose `.pipelex/` holds a full configuration that no relocated read may touch."""
    home = tmp_path / "decoy-home"
    decoy_config_dir = home / ".pipelex"
    (decoy_config_dir / "inference").mkdir(parents=True)
    (decoy_config_dir / "pipelex.toml").write_text("[decoy_marker]\nseen = true\n", encoding="utf-8")
    (decoy_config_dir / "inference" / "backends.toml").write_text("[decoy]\n", encoding="utf-8")
    (decoy_config_dir / "inference" / "routing_profiles.toml").write_text("[decoy]\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv(PIPELEX_HOME_ENV_KEY, raising=False)
    return home


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project, the working directory, with a `.pipelex/` that carries no inference files."""
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".pipelex").mkdir()
    monkeypatch.chdir(project)
    return project


def _relocated_home(tmp_path: Path) -> Path:
    """A relocated home directory with its own configuration, named unlike `.pipelex` on purpose."""
    relocated = tmp_path / "relocated-home"
    (relocated / "inference").mkdir(parents=True)
    (relocated / "pipelex.toml").write_text("[relocated_marker]\nseen = true\n", encoding="utf-8")
    (relocated / "inference" / "backends.toml").write_text("[relocated]\n", encoding="utf-8")
    (relocated / "inference" / "routing_profiles.toml").write_text("[relocated]\n", encoding="utf-8")
    return relocated


def _is_under(path: Path, directory: Path) -> bool:
    return path.resolve().is_relative_to(directory.resolve())


class TestTheResolver:
    def test_unset_is_the_dot_pipelex_directory_in_the_home_directory(self, decoy_home: Path) -> None:
        assert get_pipelex_home_dir() == decoy_home / ".pipelex"
        assert ConfigLoader().global_config_dir == decoy_home / ".pipelex"

    def test_empty_counts_as_unset(self, decoy_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, "")

        assert get_pipelex_home_dir() == decoy_home / ".pipelex"
        assert ConfigLoader().global_config_dir == decoy_home / ".pipelex"

    @pytest.mark.usefixtures("decoy_home")
    def test_an_absolute_value_names_the_directory_itself(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        relocated = tmp_path / "anywhere" / "my-home"
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(relocated))

        assert get_pipelex_home_dir() == relocated.resolve()
        assert ConfigLoader().global_config_dir == relocated.resolve()

    def test_a_tilde_value_expands_against_the_home_directory(self, decoy_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, "~/elsewhere/pipelex-home")

        assert get_pipelex_home_dir() == (decoy_home / "elsewhere" / "pipelex-home").resolve()

    @pytest.mark.usefixtures("decoy_home")
    def test_a_relative_value_resolves_against_the_working_directory(self, project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, "config/home")

        assert get_pipelex_home_dir() == (project_dir / "config" / "home").resolve()
        assert get_pipelex_home_dir().is_absolute()


@pytest.mark.usefixtures("decoy_home", "project_dir")
class TestEveryReaderFollows:
    @pytest.fixture
    def relocated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        relocated = _relocated_home(tmp_path)
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(relocated))
        return relocated.resolve()

    def test_the_configuration_layers_read_the_relocated_home_and_never_the_real_one(self, relocated: Path, decoy_home: Path) -> None:
        loader = ConfigLoader()

        home_layers = [path for path in loader.config_file_paths() if not _is_under(path, loader.pipelex_root_dir)]
        assert relocated / "pipelex.toml" in home_layers
        assert not [path for path in home_layers if _is_under(path, decoy_home)]

        merged = loader.load_config()
        assert merged.get("relocated_marker") == {"seen": True}
        assert "decoy_marker" not in merged

    def test_the_inference_files_fall_back_to_the_relocated_home(self, relocated: Path) -> None:
        loader = ConfigLoader()

        assert loader.backends_file_path == relocated / "inference" / "backends.toml"
        assert loader.routing_profiles_file_path == relocated / "inference" / "routing_profiles.toml"
        assert loader.backends_dir_path == relocated / "inference" / "backends"
        assert loader.model_decks_dir_path == relocated / "inference" / "deck"

    def test_the_inference_overrides_layer_from_the_relocated_home(self, relocated: Path, project_dir: Path, decoy_home: Path) -> None:
        loader = ConfigLoader()

        assert loader.backends_file_paths() == [
            relocated / "inference" / "backends.toml",
            relocated / "inference" / "backends_override.toml",
            (project_dir / ".pipelex" / "inference" / "backends_override.toml").resolve(),
        ]
        assert loader.routing_profiles_file_paths()[1] == relocated / "inference" / "routing_profiles_override.toml"
        every_path = loader.backends_file_paths() + loader.routing_profiles_file_paths()
        assert not [path for path in every_path if _is_under(path, decoy_home)]

    def test_existing_config_dirs_list_the_relocated_home_and_not_the_real_one(self, relocated: Path, project_dir: Path) -> None:
        assert ConfigLoader().existing_config_dirs == [relocated, (project_dir / ".pipelex").resolve()]

    def test_the_relocated_home_is_listed_once_when_it_is_the_project_directory(self, project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(project_dir / ".pipelex"))
        loader = ConfigLoader()

        assert loader.existing_config_dirs == [(project_dir / ".pipelex").resolve()]
        assert loader.backends_file_paths().count((project_dir / ".pipelex" / "inference" / "backends_override.toml").resolve()) == 1

    def test_the_first_boot_creates_the_relocated_home_from_the_kit(self, decoy_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        not_yet_there = tmp_path / "fresh" / "nested" / "home"
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(not_yet_there))
        (decoy_home / ".pipelex").rename(decoy_home / "moved-away")

        ConfigLoader().ensure_global_config_exists()

        assert (not_yet_there / "pipelex.toml").is_file()
        assert (not_yet_there / "inference" / "backends.toml").is_file()
        assert not (decoy_home / ".pipelex").exists()

    def test_pipelex_init_says_where_it_will_save_the_credentials(self, relocated: Path) -> None:
        panel = build_initialization_panel(
            needs_config=False, needs_inference=False, needs_routing=False, needs_telemetry=False, reset=False, check_credentials=True
        )
        console = Console(record=True, width=1000)
        console.print(panel)

        assert str(relocated / ".env") in console.export_text()


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


def _joins_the_home_directory_with_dot_pipelex(node: ast.AST) -> bool:
    """Whether `node` is `Path.home() / ".pipelex"` (or `/ CONFIG_DIR_NAME`), `Path.home().joinpath(".pipelex")`, or a `~/.pipelex` literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/").startswith("~/.pipelex")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_home_call(node.left) and _names_dot_pipelex(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
        return _is_home_call(node.func.value) and bool(node.args) and _names_dot_pipelex(node.args[0])
    return False


def _is_home_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "home"


def _names_dot_pipelex(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/").split("/")[0] == ".pipelex"
    return isinstance(node, ast.Name) and node.id == "CONFIG_DIR_NAME"


def _offending_joins(*, source: str, relative_path: str) -> list[str]:
    """The joins in one module outside the resolver, docstrings excluded (they describe the default, they do not compute it)."""
    tree = ast.parse(source)
    docstrings = {
        id(body[0].value)
        for owner in ast.walk(tree)
        if isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and (body := owner.body)
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    }
    allowed: set[int] = set()
    if relative_path == RESOLVER_SITE[0]:
        for owner in ast.walk(tree):
            if isinstance(owner, ast.FunctionDef) and owner.name == RESOLVER_SITE[1]:
                allowed.update(id(inner) for inner in ast.walk(owner))
    return [
        f"{relative_path}:{getattr(node, 'lineno', '?')}"
        for node in ast.walk(tree)
        if id(node) not in docstrings and id(node) not in allowed and _joins_the_home_directory_with_dot_pipelex(node)
    ]


class TestOneResolver:
    def test_the_detector_sees_every_spelling(self) -> None:
        """The control: without it, a detector that matched nothing would leave the sweep below green forever."""
        source = textwrap.dedent(
            """
            from pathlib import Path
            a = Path.home() / ".pipelex"
            b = Path.home() / CONFIG_DIR_NAME
            c = Path.home() / ".pipelex" / ".env"
            d = Path.home().joinpath(".pipelex")
            e = Path("~/.pipelex").expanduser()
            """
        )
        assert len(_offending_joins(source=source, relative_path="pipelex/somewhere.py")) == 5

    def test_nothing_but_the_resolver_joins_the_home_directory_with_dot_pipelex(self) -> None:
        offenders: list[str] = []
        for source_root in SWEPT_SOURCE_ROOTS:
            for module_path in sorted((REPO_ROOT / source_root).rglob("*.py")):
                relative_path = module_path.relative_to(REPO_ROOT).as_posix()
                offenders.extend(_offending_joins(source=module_path.read_text(encoding="utf-8"), relative_path=relative_path))
        assert not offenders, (
            f"only `{RESOLVER_SITE[0]}::{RESOLVER_SITE[1]}` may locate the home configuration directory, so that "
            f"`PIPELEX_HOME` moves it everywhere. Ask `get_pipelex_home_dir()` or `config_manager.global_config_dir` instead: "
            f"{offenders}"
        )
