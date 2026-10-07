"""The first boot lays the kit's configuration into the home configuration directory wherever it is missing.

`ConfigLoader.ensure_global_config_exists` runs on every boot that loads the layered configuration. It
copies each kit file the home lacks and never overwrites one the home has. The inference setup is one
unit, laid down only when the home has no `inference/backends.toml`, which is the file `pipelex init`
reads as "inference not set up yet". Every test points `PIPELEX_HOME` at a directory under `tmp_path`,
so none of them can reach the developer's own `~/.pipelex`.
"""

import errno
import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.models.deck_manifest import MANIFEST_FILENAME, KitManagedArea, compute_kit_manifest
from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY

_MANIFESTS = frozenset(f"inference/{area}/{MANIFEST_FILENAME}" for area in KitManagedArea)

#: Fill the home `PIPELEX_HOME` names, then say whether that loaded the manifest module.
_PROBE_MANIFEST_MODULE_IMPORT = textwrap.dedent(
    """
    import sys

    from pipelex.system.configuration.config_loader import ConfigLoader

    ConfigLoader().ensure_global_config_exists()
    print("pipelex.cogt.models.deck_manifest" in sys.modules)
    """
)


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

    @pytest.mark.parametrize(
        "unwritable_error",
        [
            pytest.param(PermissionError(errno.EACCES, "Permission denied"), id="permission_denied"),
            pytest.param(OSError(errno.EROFS, "Read-only file system"), id="read_only_file_system"),
        ],
    )
    def test_an_error_saying_the_home_cannot_be_written_is_tolerated(self, home: Path, mocker: MockerFixture, unwritable_error: OSError) -> None:
        mocker.patch.object(shutil, "copy2", side_effect=unwritable_error)

        ConfigLoader().ensure_global_config_exists()

        assert not _files_under(home)

    @pytest.mark.usefixtures("home")
    def test_any_other_error_that_stops_a_copy_is_raised(self, mocker: MockerFixture) -> None:
        disk_full = OSError(errno.ENOSPC, "No space left on device")
        mocker.patch.object(shutil, "copy2", side_effect=disk_full)

        with pytest.raises(OSError, match="No space left on device") as raised:
            ConfigLoader().ensure_global_config_exists()

        assert raised.value is disk_full

    def test_an_inference_fill_cut_short_is_completed_by_the_next_boot(self, home: Path, mocker: MockerFixture) -> None:
        """`backends.toml` is what marks the inference setup as there, so a fill that stops part-way must leave it out.

        Written before the rest, it would make every later boot take the half-copied directory for a
        complete one, and the home would fail on the missing routing profiles or deck forever.
        """
        real_copy2 = shutil.copy2

        def copy2_failing_on_one_deck_file(src: Any, dst: Any, **kwargs: Any) -> Any:
            if Path(src).name == "3_extract_deck.toml":
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_copy2(src, dst, **kwargs)

        copy2_patch = mocker.patch.object(shutil, "copy2", side_effect=copy2_failing_on_one_deck_file)
        with pytest.raises(OSError, match="No space left on device"):
            ConfigLoader().ensure_global_config_exists()
        assert not (home / "inference" / "backends.toml").exists()
        mocker.stop(copy2_patch)

        ConfigLoader().ensure_global_config_exists()

        installed = _files_under(home)
        kit_files = _kit_files()
        assert set(installed) == set(kit_files) | _MANIFESTS
        assert {path: installed[path] for path in kit_files} == kit_files

    @pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default")
    @pytest.mark.parametrize(
        "kit_file",
        [
            "pipelex.toml",
            "inference/deck/1_llm_deck.toml",
            "inference/backends.toml",
            f"inference/{KitManagedArea.DECK}/{MANIFEST_FILENAME}",
            f"inference/{KitManagedArea.BACKENDS}/{MANIFEST_FILENAME}",
        ],
    )
    @pytest.mark.parametrize("link_target_dir_exists", [False, True])
    def test_a_dangling_link_where_a_kit_file_goes_is_kept_and_never_written_through(
        self, home: Path, tmp_path: Path, kit_file: str, link_target_dir_exists: bool
    ) -> None:
        """A link is the user's, even one whose target is gone: copying or stamping through it would fail every boot, or write elsewhere."""
        link_target_dir = tmp_path / "link-target"
        if link_target_dir_exists:
            link_target_dir.mkdir()
        link_target = link_target_dir / "gone.toml"
        link = home / kit_file
        link.parent.mkdir(parents=True)
        link.symlink_to(link_target)

        ConfigLoader().ensure_global_config_exists()

        assert link.is_symlink()
        assert link.readlink() == link_target
        assert not link_target.exists()
        assert link_target_dir.exists() == link_target_dir_exists

    @pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link takes a privilege Windows does not grant by default")
    @pytest.mark.parametrize("kit_directory", ["inference", "inference/deck", "inference/backends"])
    @pytest.mark.parametrize("entry_kind", ["link_to_a_directory", "dangling_link", "regular_file"])
    def test_whatever_stands_where_a_kit_directory_goes_is_left_alone_with_everything_under_it(
        self, home: Path, tmp_path: Path, kit_directory: str, entry_kind: str
    ) -> None:
        """The fill never enters a link, valid or dangling, and never replaces a file standing where the kit has a directory.

        Entering a valid link would copy the kit into wherever it points, and a dangling one or a file would
        make creating the directory fail on every boot. What stands there is the user's, and the rest of the
        home is still filled.
        """
        entry = home / kit_directory
        entry.parent.mkdir(parents=True)
        link_target = tmp_path / "elsewhere"
        match entry_kind:
            case "link_to_a_directory":
                link_target.mkdir()
                entry.symlink_to(link_target, target_is_directory=True)
            case "dangling_link":
                entry.symlink_to(link_target, target_is_directory=True)
            case _:
                entry.write_text("not a directory\n", encoding="utf-8")

        ConfigLoader().ensure_global_config_exists()

        match entry_kind:
            case "link_to_a_directory":
                assert entry.is_symlink()
                assert entry.readlink() == link_target
                assert not list(link_target.iterdir())
            case "dangling_link":
                assert entry.is_symlink()
                assert entry.readlink() == link_target
                assert not link_target.exists()
            case _:
                assert entry.read_text(encoding="utf-8") == "not a directory\n"
        assert (home / "pipelex.toml").read_bytes() == _kit_files()["pipelex.toml"]

    @pytest.mark.parametrize("kit_file", ["pipelex.toml", "inference/deck/3_extract_deck.toml", "inference/backends.toml"])
    def test_a_copy_cut_off_mid_write_leaves_no_partial_file_and_the_next_boot_completes_it(
        self, home: Path, mocker: MockerFixture, kit_file: str
    ) -> None:
        """A file appears whole or not at all: a truncated `backends.toml` above all would pass for a finished inference setup."""
        real_copy2 = shutil.copy2

        def copy2_cut_off_mid_write(src: Any, dst: Any, **kwargs: Any) -> Any:
            if Path(src).as_posix().endswith(f"/configs/{kit_file}"):
                Path(dst).write_bytes(Path(src).read_bytes()[:16])
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_copy2(src, dst, **kwargs)

        copy2_patch = mocker.patch.object(shutil, "copy2", side_effect=copy2_cut_off_mid_write)
        with pytest.raises(OSError, match="No space left on device"):
            ConfigLoader().ensure_global_config_exists()
        # Every file left behind is a whole kit file or a manifest: no truncated copy, and no temporary one.
        kit_files = _kit_files()
        installed = _files_under(home)
        assert kit_file not in installed
        assert set(installed) <= set(kit_files) | _MANIFESTS
        assert {path: content for path, content in installed.items() if path in kit_files} == {
            path: kit_files[path] for path in installed if path in kit_files
        }
        mocker.stop(copy2_patch)

        ConfigLoader().ensure_global_config_exists()

        installed = _files_under(home)
        assert set(installed) == set(kit_files) | _MANIFESTS
        assert {path: installed[path] for path in kit_files} == kit_files

    @pytest.mark.parametrize(
        ("home_is_filled", "expects_manifest_module"),
        [
            pytest.param(True, False, id="filled_home_imports_nothing_more"),
            pytest.param(False, True, id="control_empty_home_stamps_manifests"),
        ],
    )
    def test_a_filled_home_does_not_import_the_manifest_module(self, home: Path, home_is_filled: bool, expects_manifest_module: bool) -> None:
        """The manifest module pulls in the inference backend chain, and only a home being filled needs it.

        Asked in a fresh interpreter, because this one imported it long ago. The empty-home control proves the
        probe sees the import when it happens, so the filled case cannot pass for a probe that sees nothing.
        """
        if home_is_filled:
            ConfigLoader().ensure_global_config_exists()
        else:
            home.mkdir()

        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", _PROBE_MANIFEST_MODULE_IMPORT],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env={**os.environ, PIPELEX_HOME_ENV_KEY: str(home)},
        )

        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        assert result.stdout.strip().splitlines()[-1] == str(expects_manifest_module)
