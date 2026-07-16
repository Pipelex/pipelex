"""Unit tests for doctor's deck sync check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.commands.doctor_cmd import check_deck_sync
from pipelex.cogt.models.deck_manifest import DeckFileStatus, DeckSyncReport

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestCheckDeckSync:
    def _make_deck_dir(self, tmp_path: Path) -> Path:
        deck_dir = tmp_path / "inference" / "deck"
        deck_dir.mkdir(parents=True)
        return deck_dir

    def test_deck_dir_missing_is_healthy(self, tmp_path: Path) -> None:
        """A missing deck dir defers to the config checks and reports healthy."""
        healthy, report, message = check_deck_sync(config_dir=tmp_path)

        assert healthy is True
        assert report.manifest_present is False
        assert message == "Deck directory not present"

    def test_clean_deck(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A clean deck is healthy and names the kit version."""
        self._make_deck_dir(tmp_path)
        clean_report = DeckSyncReport(
            kit_version="1.2.0",
            installed_kit_version="1.2.0",
            manifest_present=True,
            files={"deck.toml": DeckFileStatus.UP_TO_DATE},
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.compute_deck_sync_report", return_value=clean_report)

        healthy, report, message = check_deck_sync(config_dir=tmp_path)

        assert healthy is True
        assert report is clean_report
        assert message == "Deck is up to date with pipelex 1.2.0"

    def test_manifest_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A deck without a manifest points the user at `pipelex update`."""
        self._make_deck_dir(tmp_path)
        dirty_report = DeckSyncReport(
            kit_version="1.2.0",
            installed_kit_version=None,
            manifest_present=False,
            files={"deck.toml": DeckFileStatus.LOCALLY_MODIFIED},
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.compute_deck_sync_report", return_value=dirty_report)

        healthy, _, message = check_deck_sync(config_dir=tmp_path)

        assert healthy is False
        assert "Deck manifest missing" in message
        assert "pipelex update" in message

    def test_kit_version_mismatch(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A version-skewed deck reports both versions and the actionable file count."""
        self._make_deck_dir(tmp_path)
        dirty_report = DeckSyncReport(
            kit_version="1.3.0",
            installed_kit_version="1.2.0",
            manifest_present=True,
            files={
                "deck.toml": DeckFileStatus.CLEAN_BEHIND,
                "extra.toml": DeckFileStatus.KIT_ADDED,
                "ok.toml": DeckFileStatus.UP_TO_DATE,
            },
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.compute_deck_sync_report", return_value=dirty_report)

        healthy, _, message = check_deck_sync(config_dir=tmp_path)

        assert healthy is False
        assert message == "Deck installed for pipelex 1.2.0, current is 1.3.0 (2 file(s) need action)"

    def test_same_version_with_actionable_files(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A same-version deck with modified files reports the actionable count."""
        self._make_deck_dir(tmp_path)
        dirty_report = DeckSyncReport(
            kit_version="1.2.0",
            installed_kit_version="1.2.0",
            manifest_present=True,
            files={"deck.toml": DeckFileStatus.LOCALLY_MODIFIED},
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.compute_deck_sync_report", return_value=dirty_report)

        healthy, _, message = check_deck_sync(config_dir=tmp_path)

        assert healthy is False
        assert message == "1 deck file(s) need action"
