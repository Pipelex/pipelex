from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.models import deck_manifest
from pipelex.cogt.models.deck_manifest import (
    MANIFEST_FILENAME,
    DeckFileStatus,
    DeckManifest,
    compute_deck_sync_report,
    compute_file_sha256,
    compute_kit_manifest,
    is_deck_stale_fast,
    list_managed_installed_files,
    list_managed_kit_files,
    manifest_path,
    read_manifest,
    suggest_x_custom_filename,
    write_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestDeckManifest:
    @staticmethod
    def _seed_kit(mocker: MockerFixture, kit_dir: Path, files: dict[str, str]) -> None:
        kit_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (kit_dir / filename).write_text(content, encoding="utf-8")
        mocker.patch.object(deck_manifest, "kit_deck_dir", return_value=kit_dir)

    @staticmethod
    def _seed_installed(deck_dir: Path, files: dict[str, str]) -> None:
        deck_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (deck_dir / filename).write_text(content, encoding="utf-8")

    def test_manifest_round_trip(self, tmp_path: Path) -> None:
        manifest = DeckManifest(kit_version="1.2.3", files={"1_llm_deck.toml": "hash-a", "2_img_gen_deck.toml": "hash-b"})
        deck_dir = tmp_path / "deck"
        write_manifest(deck_dir, manifest)
        assert manifest_path(deck_dir).is_file()

        reloaded = read_manifest(deck_dir)
        assert reloaded == manifest

    def test_read_manifest_missing(self, tmp_path: Path) -> None:
        assert read_manifest(tmp_path / "absent") is None

    def test_read_manifest_corrupt(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        (deck_dir / MANIFEST_FILENAME).write_text("not json {", encoding="utf-8")
        assert read_manifest(deck_dir) is None

    def test_read_manifest_invalid_schema(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        (deck_dir / MANIFEST_FILENAME).write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")
        assert read_manifest(deck_dir) is None

    def test_compute_file_sha256_is_deterministic(self, tmp_path: Path) -> None:
        target = tmp_path / "f.toml"
        target.write_text("hello", encoding="utf-8")
        first = compute_file_sha256(target)
        second = compute_file_sha256(target)
        assert first == second
        assert len(first) == 64

    def test_managed_filter_only_admits_numbered_files(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        self._seed_kit(
            mocker,
            kit_dir,
            {
                "1_llm_deck.toml": "managed",
                "2_img_gen_deck.toml": "managed",
                "x_custom_llm_deck.toml": "user-owned",
                "x_custom_extract_deck.toml": "user-owned",
                "cookbook.toml": "user-owned",
                "not_numbered.toml": "user-owned",
                ".DS_Store": "junk",
            },
        )
        kit_files = list_managed_kit_files()
        assert set(kit_files.keys()) == {"1_llm_deck.toml", "2_img_gen_deck.toml"}

    def test_list_managed_installed_files_filters_same_way(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        self._seed_installed(
            deck_dir,
            {
                "1_llm_deck.toml": "a",
                "x_custom_llm_deck.toml": "b",
                "cookbook.toml": "c",
            },
        )
        installed = list_managed_installed_files(deck_dir)
        assert set(installed.keys()) == {"1_llm_deck.toml"}

    def test_list_managed_installed_files_ignores_non_numbered_user_tomls(self, tmp_path: Path) -> None:
        """Only numbered ``<digits>_*.toml`` files are kit-managed. A user TOML without the
        numbered prefix and without the ``x_custom_`` prefix must be left alone so it isn't
        reported / overwritten as if it were a kit file.
        """
        deck_dir = tmp_path / "deck"
        self._seed_installed(
            deck_dir,
            {
                "1_llm_deck.toml": "managed",
                "my_overrides.toml": "user-authored",
                "notes.toml": "user-authored",
            },
        )
        installed = list_managed_installed_files(deck_dir)
        assert set(installed.keys()) == {"1_llm_deck.toml"}

    def test_list_managed_installed_files_missing_dir(self, tmp_path: Path) -> None:
        assert list_managed_installed_files(tmp_path / "absent") == {}

    def test_compute_kit_manifest_stamps_version(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "content-a"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="9.9.9")

        manifest = compute_kit_manifest()
        assert manifest.kit_version == "9.9.9"
        assert "1_llm_deck.toml" in manifest.files

    def test_sync_report_up_to_date(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        contents = {"1_llm_deck.toml": "same-everywhere"}
        self._seed_kit(mocker, kit_dir, contents)
        self._seed_installed(deck_dir, contents)
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")
        write_manifest(deck_dir, compute_kit_manifest())

        report = compute_deck_sync_report(deck_dir)
        assert report.is_clean()
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.UP_TO_DATE

    def test_sync_report_clean_behind(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "old"})
        self._seed_installed(deck_dir, {"1_llm_deck.toml": "old"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")
        write_manifest(deck_dir, compute_kit_manifest())

        # Simulate a kit upgrade — the file content has moved on but the user has not edited theirs.
        (kit_dir / "1_llm_deck.toml").write_text("new", encoding="utf-8")
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.1.0")

        report = compute_deck_sync_report(deck_dir)
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.CLEAN_BEHIND
        assert not report.is_clean()
        assert report.installed_kit_version == "1.0.0"

    def test_sync_report_locally_modified(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "kit-version"})
        self._seed_installed(deck_dir, {"1_llm_deck.toml": "kit-version"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")
        write_manifest(deck_dir, compute_kit_manifest())

        # User edits their installed file, kit unchanged.
        (deck_dir / "1_llm_deck.toml").write_text("user-edited", encoding="utf-8")

        report = compute_deck_sync_report(deck_dir)
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.LOCALLY_MODIFIED

    def test_sync_report_kit_added(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "a", "5_new_deck.toml": "fresh"})
        self._seed_installed(deck_dir, {"1_llm_deck.toml": "a"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")
        # Manifest captures only the file that existed at install time.
        write_manifest(deck_dir, DeckManifest(kit_version="1.0.0", files={"1_llm_deck.toml": compute_file_sha256(deck_dir / "1_llm_deck.toml")}))

        report = compute_deck_sync_report(deck_dir)
        assert report.files["5_new_deck.toml"] == DeckFileStatus.KIT_ADDED
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.UP_TO_DATE

    def test_sync_report_kit_removed(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "a"})
        self._seed_installed(deck_dir, {"1_llm_deck.toml": "a", "9_retired_deck.toml": "old"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.1.0")
        write_manifest(
            deck_dir,
            DeckManifest(
                kit_version="1.0.0",
                files={
                    "1_llm_deck.toml": compute_file_sha256(deck_dir / "1_llm_deck.toml"),
                    "9_retired_deck.toml": compute_file_sha256(deck_dir / "9_retired_deck.toml"),
                },
            ),
        )

        report = compute_deck_sync_report(deck_dir)
        assert report.files["9_retired_deck.toml"] == DeckFileStatus.KIT_REMOVED
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.UP_TO_DATE

    def test_sync_report_ignores_user_added_files(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "kit"})
        self._seed_installed(deck_dir, {"1_llm_deck.toml": "kit", "cookbook.toml": "user-content"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")
        write_manifest(deck_dir, compute_kit_manifest())

        report = compute_deck_sync_report(deck_dir)
        assert "cookbook.toml" not in report.files
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.UP_TO_DATE

    def test_sync_report_no_manifest_treats_matching_files_as_up_to_date(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        contents = {"1_llm_deck.toml": "identical"}
        self._seed_kit(mocker, kit_dir, contents)
        self._seed_installed(deck_dir, contents)
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")

        report = compute_deck_sync_report(deck_dir)
        assert report.manifest_present is False
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.UP_TO_DATE
        # No manifest means the report still cannot be considered "clean" — boot warn still fires.
        assert not report.is_clean()

    def test_sync_report_no_manifest_marks_drift_as_locally_modified(self, mocker: MockerFixture, tmp_path: Path) -> None:
        kit_dir = tmp_path / "kit"
        deck_dir = tmp_path / "deck"
        self._seed_kit(mocker, kit_dir, {"1_llm_deck.toml": "kit"})
        self._seed_installed(deck_dir, {"1_llm_deck.toml": "drift"})
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.0.0")

        report = compute_deck_sync_report(deck_dir)
        assert report.manifest_present is False
        assert report.files["1_llm_deck.toml"] == DeckFileStatus.LOCALLY_MODIFIED

    @pytest.mark.parametrize(
        ("manifest_version", "current_version", "expected_stale"),
        [
            ("1.0.0", "1.0.0", False),
            ("1.0.0", "1.1.0", True),
            ("1.0.0", "2.0.0", True),
            # Downgrade: manifest newer than installed — no warn.
            ("2.0.0", "1.5.0", False),
            # Editable / dev builds carry build metadata; cores match, so not stale.
            ("1.0.0", "1.0.0+localdev", False),
            ("1.0.0+ci.42", "1.0.0", False),
            # Pre-release suffixes are also ignored for the boot check.
            ("1.0.0-rc1", "1.0.0", False),
        ],
    )
    def test_is_deck_stale_fast(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        manifest_version: str,
        current_version: str,
        expected_stale: bool,
    ) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        write_manifest(deck_dir, DeckManifest(kit_version=manifest_version, files={}))
        mocker.patch.object(deck_manifest, "get_package_version", return_value=current_version)

        assert is_deck_stale_fast(deck_dir) is expected_stale

    def test_is_deck_stale_fast_missing_manifest(self, tmp_path: Path) -> None:
        deck_dir = tmp_path / "deck"
        deck_dir.mkdir()
        # No manifest at all — should be treated as stale so the user gets the migration warn.
        assert is_deck_stale_fast(deck_dir) is True

    @pytest.mark.parametrize(
        ("numbered_filename", "expected_override"),
        [
            ("1_llm_deck.toml", "x_custom_llm_deck.toml"),
            ("2_img_gen_deck.toml", "x_custom_img_gen_deck.toml"),
            ("3_extract_deck.toml", "x_custom_extract_deck.toml"),
            ("4_search_deck.toml", "x_custom_search_deck.toml"),
            # Unconventional names fall back to the generic suggestion.
            ("not_numbered.toml", "x_custom_*.toml"),
            ("5.toml", "x_custom_*.toml"),
        ],
    )
    def test_suggest_x_custom_filename(self, numbered_filename: str, expected_override: str) -> None:
        assert suggest_x_custom_filename(numbered_filename) == expected_override
