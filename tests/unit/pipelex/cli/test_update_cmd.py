from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands import update_cmd as update_cmd_module
from pipelex.cli.commands.update_cmd import update_cmd
from pipelex.cogt.models import deck_manifest
from pipelex.cogt.models.deck_manifest import (
    MANIFEST_FILENAME,
    DeckManifest,
    is_deck_stale_fast,
    write_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestUpdateCmd:
    @staticmethod
    def _seed_kit(mocker: MockerFixture, kit_dir: Path, files: dict[str, str]) -> None:
        kit_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (kit_dir / filename).write_text(content, encoding="utf-8")
        mocker.patch.object(deck_manifest, "kit_deck_dir", return_value=kit_dir)

    @staticmethod
    def _seed_kit_backends(mocker: MockerFixture, kit_backends_dir: Path, files: dict[str, str]) -> None:
        kit_backends_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (kit_backends_dir / filename).write_text(content, encoding="utf-8")
        mocker.patch.object(deck_manifest, "kit_backends_dir", return_value=kit_backends_dir)

    @staticmethod
    def _seed_installed(deck_dir: Path, files: dict[str, str]) -> None:
        deck_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (deck_dir / filename).write_text(content, encoding="utf-8")

    @staticmethod
    def _patch_resolve_deck_dir(mocker: MockerFixture, deck_dir: Path) -> None:
        mocker.patch.object(update_cmd_module, "_resolve_deck_dir", return_value=deck_dir)

    @staticmethod
    def _patch_resolve_backends_dir(mocker: MockerFixture, backends_dir: Path) -> None:
        mocker.patch.object(update_cmd_module, "_resolve_backends_dir", return_value=backends_dir)

    @staticmethod
    def _patch_version(mocker: MockerFixture, version: str) -> None:
        mocker.patch.object(deck_manifest, "get_package_version", return_value=version)

    @pytest.fixture
    def kit_and_deck(self, mocker: MockerFixture, tmp_path: Path) -> tuple[Path, Path]:
        """Materialize a kit with one numbered file and an installed deck dir mirroring it, and no installed backends dir."""
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        contents = {"1_llm_deck.toml": "v1-content"}
        self._seed_kit(mocker, kit_dir, contents)
        self._seed_installed(deck_dir, contents)
        self._patch_resolve_deck_dir(mocker, deck_dir)
        # Never the real backends directory: an absent one is skipped, and the backends tests seed their own.
        self._patch_resolve_backends_dir(mocker, tmp_path / "no-backends")
        self._patch_version(mocker, "1.0.0")
        return kit_dir, deck_dir

    @pytest.fixture
    def kit_and_backends(self, mocker: MockerFixture, tmp_path: Path, kit_and_deck: tuple[Path, Path]) -> tuple[Path, Path]:
        """Materialize a kit backends dir and an installed one whose internal.toml predates the kit's, with no backends manifest.

        The deck is left in sync with its manifest, so only the internal backend needs an update.
        """
        _, deck_dir = kit_and_deck
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        kit_backends_dir = tmp_path / "kit-backends"
        backends_dir = tmp_path / "backends"
        self._seed_kit_backends(
            mocker,
            kit_backends_dir,
            {"internal.toml": "internal-with-reportlab", "openai.toml": "openai-kit", "models_reference.md": "models-kit"},
        )
        self._seed_installed(backends_dir, {"internal.toml": "internal-before-reportlab", "openai.toml": "openai-user", "my_backend.toml": "mine"})
        self._patch_resolve_backends_dir(mocker, backends_dir)
        return kit_backends_dir, backends_dir

    def test_dry_run_makes_no_changes(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        # Kit has moved on, but the install hasn't yet.
        (kit_dir / "1_llm_deck.toml").write_text("v2-content", encoding="utf-8")
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        self._patch_version(mocker, "1.1.0")

        update_cmd(dry_run=True)

        assert (deck_dir / "1_llm_deck.toml").read_text(encoding="utf-8") == "v1-content"

    def test_clean_state_writes_baseline_manifest(self, kit_and_deck: tuple[Path, Path]) -> None:
        _, deck_dir = kit_and_deck
        # No manifest yet — migration baseline should be written.
        assert not (deck_dir / MANIFEST_FILENAME).exists()

        update_cmd(yes=True)

        assert (deck_dir / MANIFEST_FILENAME).is_file()
        assert is_deck_stale_fast(deck_dir) is False

    def test_clean_behind_overwrites_without_backup(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        (kit_dir / "1_llm_deck.toml").write_text("v2-content", encoding="utf-8")
        self._patch_version(mocker, "1.1.0")

        update_cmd(yes=True)

        assert (deck_dir / "1_llm_deck.toml").read_text(encoding="utf-8") == "v2-content"
        assert not list(deck_dir.glob("*.bak.*"))
        assert is_deck_stale_fast(deck_dir) is False

    def test_locally_modified_creates_backup_and_overwrites(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        (deck_dir / "1_llm_deck.toml").write_text("user-edits", encoding="utf-8")
        (kit_dir / "1_llm_deck.toml").write_text("v2-content", encoding="utf-8")
        self._patch_version(mocker, "1.1.0")

        update_cmd(yes=True)

        backups = sorted(deck_dir.glob("1_llm_deck.toml.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "user-edits"
        assert re.match(r"1_llm_deck\.toml\.bak\.\d{8}T\d{6}Z", backups[0].name) is not None
        assert (deck_dir / "1_llm_deck.toml").read_text(encoding="utf-8") == "v2-content"

    def test_no_backup_flag_skips_backup(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        (deck_dir / "1_llm_deck.toml").write_text("user-edits", encoding="utf-8")
        (kit_dir / "1_llm_deck.toml").write_text("v2-content", encoding="utf-8")
        self._patch_version(mocker, "1.1.0")

        update_cmd(yes=True, no_backup=True)

        assert not list(deck_dir.glob("*.bak.*"))
        assert (deck_dir / "1_llm_deck.toml").read_text(encoding="utf-8") == "v2-content"

    def test_kit_added_installs_new_file(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        (kit_dir / "5_new_deck.toml").write_text("brand-new", encoding="utf-8")
        self._patch_version(mocker, "1.1.0")

        update_cmd(yes=True)

        assert (deck_dir / "5_new_deck.toml").read_text(encoding="utf-8") == "brand-new"

    def test_kit_removed_backs_up_then_deletes(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        _, deck_dir = kit_and_deck
        (deck_dir / "9_retired_deck.toml").write_text("retired-content", encoding="utf-8")
        write_manifest(
            DeckManifest(
                kit_version="1.0.0",
                files={
                    "1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml"),
                    "9_retired_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "9_retired_deck.toml"),
                },
            ),
            installed_dir=deck_dir,
        )
        self._patch_version(mocker, "1.1.0")

        update_cmd(yes=True)

        assert not (deck_dir / "9_retired_deck.toml").exists()
        backups = sorted(deck_dir.glob("9_retired_deck.toml.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "retired-content"

    def test_x_custom_files_are_left_alone(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        (deck_dir / "x_custom_llm_deck.toml").write_text("user-overrides", encoding="utf-8")
        (kit_dir / "1_llm_deck.toml").write_text("v2-content", encoding="utf-8")
        self._patch_version(mocker, "1.1.0")

        update_cmd(yes=True)

        assert (deck_dir / "x_custom_llm_deck.toml").read_text(encoding="utf-8") == "user-overrides"

    def test_yes_flag_skips_confirm(self, mocker: MockerFixture, kit_and_deck: tuple[Path, Path]) -> None:
        kit_dir, deck_dir = kit_and_deck
        write_manifest(
            DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": deck_manifest.compute_file_sha256(deck_dir / "1_llm_deck.toml")}),
            installed_dir=deck_dir,
        )
        (kit_dir / "1_llm_deck.toml").write_text("v2-content", encoding="utf-8")
        self._patch_version(mocker, "1.1.0")

        confirm_spy = mocker.patch.object(update_cmd_module.Confirm, "ask")
        update_cmd(yes=True)

        confirm_spy.assert_not_called()

    def test_missing_deck_dir_exits_with_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        absent = tmp_path / "nope"
        self._patch_resolve_deck_dir(mocker, absent)
        with pytest.raises(SystemExit) as exit_info:
            update_cmd(yes=True)
        assert exit_info.value.code == 1

    def test_a_stale_internal_toml_is_refreshed_with_a_backup(self, kit_and_backends: tuple[Path, Path]) -> None:
        """An internal.toml from before this release has no manifest entry and differs from the kit: backed up, then refreshed."""
        _, backends_dir = kit_and_backends

        update_cmd(yes=True)

        assert (backends_dir / "internal.toml").read_text(encoding="utf-8") == "internal-with-reportlab"
        backups = sorted(backends_dir.glob("internal.toml.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "internal-before-reportlab"
        assert re.match(r"internal\.toml\.bak\.\d{8}T\d{6}Z", backups[0].name) is not None
        assert (backends_dir / MANIFEST_FILENAME).is_file()

    def test_a_stale_internal_toml_is_refreshed_without_a_backup_under_no_backup(self, kit_and_backends: tuple[Path, Path]) -> None:
        _, backends_dir = kit_and_backends

        update_cmd(yes=True, no_backup=True)

        assert (backends_dir / "internal.toml").read_text(encoding="utf-8") == "internal-with-reportlab"
        assert not list(backends_dir.glob("*.bak.*"))

    def test_other_backend_files_are_left_alone(self, kit_and_backends: tuple[Path, Path]) -> None:
        """Only internal.toml is managed: a kit backend file the user edited, and one of their own, stay as they are."""
        _, backends_dir = kit_and_backends

        update_cmd(yes=True)

        assert (backends_dir / "openai.toml").read_text(encoding="utf-8") == "openai-user"
        assert (backends_dir / "my_backend.toml").read_text(encoding="utf-8") == "mine"
        assert not (backends_dir / "models_reference.md").exists()
        assert sorted(path.name for path in backends_dir.glob("*.bak.*")) == [next(backends_dir.glob("internal.toml.bak.*")).name]

    def test_a_refreshed_internal_toml_is_up_to_date_afterwards(self, kit_and_backends: tuple[Path, Path]) -> None:
        """The update writes the backends manifest, so the next run finds nothing to do and the dry run changes nothing."""
        _, backends_dir = kit_and_backends
        update_cmd(yes=True)
        refreshed_mtime = (backends_dir / "internal.toml").stat().st_mtime_ns

        report = deck_manifest.compute_sync_report(backends_dir, area=deck_manifest.KitManagedArea.BACKENDS)
        update_cmd(dry_run=True)

        assert report.is_clean()
        assert (backends_dir / "internal.toml").stat().st_mtime_ns == refreshed_mtime

    def test_a_dry_run_leaves_a_stale_internal_toml_as_it_is(self, kit_and_backends: tuple[Path, Path]) -> None:
        _, backends_dir = kit_and_backends

        update_cmd(dry_run=True)

        assert (backends_dir / "internal.toml").read_text(encoding="utf-8") == "internal-before-reportlab"
        assert not (backends_dir / MANIFEST_FILENAME).exists()
