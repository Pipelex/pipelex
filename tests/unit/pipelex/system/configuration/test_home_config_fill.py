"""The first boot lays the kit's configuration into the home configuration directory wherever it is missing.

`ConfigLoader.ensure_global_config_exists` runs on every boot that loads the layered configuration. It
copies each kit file the home lacks and never overwrites one the home has. The inference setup is one
unit, laid down only when the home has no `inference/backends.toml`, which is the file `pipelex init`
reads as "inference not set up yet". Every test points `PIPELEX_HOME` at a directory under `tmp_path`,
so none of them can reach the developer's own `~/.pipelex`.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from pipelex.cogt.models.deck_manifest import MANIFEST_FILENAME, KitManagedArea, compute_kit_manifest
from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY

_MANIFESTS = frozenset(f"inference/{area}/{MANIFEST_FILENAME}" for area in KitManagedArea)


def _kit_files() -> dict[str, bytes]:
    """Every file a fresh home receives from the kit as it is, by its path relative to the kit's `configs/`.

    The kit's own `.kit_manifest.json` files are not among them: a manifest records one install, so the
    home's are written for it rather than copied from whatever the kit's say.
    """
    kit_dir = Path(str(get_kit_configs_dir()))
    return {
        path.relative_to(kit_dir).as_posix(): path.read_bytes()
        for path in kit_dir.rglob("*")
        if path.is_file() and not (GIT_IGNORED_CONFIG_FILES | {MANIFEST_FILENAME}).intersection(path.relative_to(kit_dir).parts)
    }


def _files_under(directory: Path) -> dict[str, bytes]:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def _write_files(directory: Path, *, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        target = directory / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class TestHomeConfigFill:
    @pytest.fixture
    def home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """The home configuration directory, which each test creates (or not) for itself."""
        home = tmp_path / "pipelex-home"
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
        return home

    @pytest.mark.parametrize("home_exists", [False, True])
    def test_an_absent_or_empty_home_receives_the_whole_kit(self, home: Path, home_exists: bool) -> None:
        if home_exists:
            home.mkdir()

        ConfigLoader().ensure_global_config_exists()

        installed = _files_under(home)
        kit_files = _kit_files()
        assert set(installed) == set(kit_files) | _MANIFESTS
        assert {path: installed[path] for path in kit_files} == kit_files
        for area in KitManagedArea:
            stamped = json.loads((home / "inference" / area / MANIFEST_FILENAME).read_text(encoding="utf-8"))
            assert stamped == compute_kit_manifest(area=area).model_dump()

    @pytest.mark.parametrize(
        "unrelated_files",
        [
            pytest.param({"pipelex_service.toml": "[agreement]\nterms_accepted = true\n"}, id="retired_service_file"),
            pytest.param({".env": "OPENAI_API_KEY=sk-test\n"}, id="credentials"),
            pytest.param({"pipelex_override.toml": "[runtime.log]\ndefault_log_level = 'DEBUG'\n"}, id="personal_override"),
            pytest.param({"inference/backends_override.toml": "[openai]\nenabled = true\n"}, id="inference_override_only"),
        ],
    )
    def test_a_home_holding_only_unrelated_files_receives_the_whole_kit_beside_them(self, home: Path, unrelated_files: dict[str, str]) -> None:
        """A home holding only files the kit does not ship boots like a fresh one, and keeps those files."""
        _write_files(home, files=unrelated_files)

        ConfigLoader().ensure_global_config_exists()

        installed = _files_under(home)
        kit_files = _kit_files()
        assert set(installed) == set(kit_files) | _MANIFESTS | set(unrelated_files)
        assert {path: installed[path] for path in kit_files} == kit_files
        assert {path: installed[path].decode("utf-8") for path in unrelated_files} == unrelated_files

    @pytest.mark.parametrize(
        "user_file",
        [
            "pipelex.toml",
            "telemetry.toml",
            "inference/routing_profiles.toml",
            "inference/deck/1_llm_deck.toml",
            "inference/backends/openai.toml",
        ],
    )
    def test_a_kit_file_the_user_changed_is_kept_and_the_rest_is_filled_in(self, home: Path, user_file: str) -> None:
        user_content = "# the user's own version of this file\n"
        _write_files(home, files={user_file: user_content})

        ConfigLoader().ensure_global_config_exists()

        installed = _files_under(home)
        kit_files = _kit_files()
        assert installed[user_file].decode("utf-8") == user_content
        assert set(installed) == set(kit_files) | _MANIFESTS
        assert {path: installed[path] for path in kit_files if path != user_file} == {
            path: content for path, content in kit_files.items() if path != user_file
        }

    def test_a_home_with_its_own_backends_keeps_its_inference_directory_whole(self, home: Path) -> None:
        """Only the inference unit is all-or-nothing: the configuration files beside it are still filled in.

        Copying the kit's routing profiles, deck or backend files beside a `backends.toml` the user set up
        could route to, or alias models of, backends that file disables, so the inference directory of a
        home that has one is left exactly as it is.
        """
        user_backends = "[anthropic]\nenabled = true\n"
        _write_files(home, files={"inference/backends.toml": user_backends})

        ConfigLoader().ensure_global_config_exists()

        assert _files_under(home / "inference") == {"backends.toml": user_backends.encode("utf-8")}
        kit_files = _kit_files()
        top_level_kit_files = {path: content for path, content in kit_files.items() if not path.startswith("inference/")}
        assert top_level_kit_files
        assert {path: content for path, content in _files_under(home).items() if not path.startswith("inference/")} == top_level_kit_files

    def test_a_manifest_already_in_an_area_is_kept_and_the_area_without_one_is_stamped(self, home: Path) -> None:
        recorded_manifest = json.dumps({"kit_version": "0.0.1", "files": {}}, indent=2, sort_keys=True) + "\n"
        deck_manifest = f"inference/{KitManagedArea.DECK}/{MANIFEST_FILENAME}"
        backends_manifest = f"inference/{KitManagedArea.BACKENDS}/{MANIFEST_FILENAME}"
        _write_files(home, files={deck_manifest: recorded_manifest})

        ConfigLoader().ensure_global_config_exists()

        assert (home / deck_manifest).read_text(encoding="utf-8") == recorded_manifest
        stamped = json.loads((home / backends_manifest).read_text(encoding="utf-8"))
        assert stamped == compute_kit_manifest(area=KitManagedArea.BACKENDS).model_dump()

    def test_a_home_holding_every_kit_file_is_not_written(self, home: Path) -> None:
        loader = ConfigLoader()
        loader.ensure_global_config_exists()
        (home / "pipelex.toml").write_text("# edited by the user\n", encoding="utf-8")
        # A rewrite by `shutil.copy2` would carry the kit file's own timestamp, so pinning every file to
        # one far from it makes any rewrite visible, even of a file whose content would not change.
        pinned_ns = 1_000_000_000_000_000_000
        for path in home.rglob("*"):
            if path.is_file():
                os.utime(path, ns=(pinned_ns, pinned_ns))
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in home.rglob("*") if path.is_file()}

        loader.ensure_global_config_exists()

        assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in home.rglob("*") if path.is_file()} == before

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits do not make a Windows directory read-only")
    @pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason="root writes through POSIX permission bits")
    def test_an_existing_home_the_process_cannot_write_to_is_read_as_it_is(self, home: Path) -> None:
        """A home mounted read-only, or owned by another user, must not stop a boot over a file it lacks."""
        ConfigLoader().ensure_global_config_exists()
        (home / "plxt.toml").unlink()
        home.chmod(0o555)
        try:
            ConfigLoader().ensure_global_config_exists()

            assert not (home / "plxt.toml").exists()
        finally:
            home.chmod(0o755)
