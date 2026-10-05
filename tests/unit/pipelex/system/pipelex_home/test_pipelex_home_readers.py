"""Every reader of the home configuration directory follows `PIPELEX_HOME`, through `ConfigLoader.global_config_dir`.

The configuration layers, the inference files and their overrides, the first-boot copy of the kit,
`existing_config_dirs` (and so `pipelex migrate`) and the `pipelex init` panel all move with it, and
none of them reads the decoy home that `decoy_home` stands in for the real one.
"""

from pathlib import Path

import pytest
from rich.console import Console

from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY


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
