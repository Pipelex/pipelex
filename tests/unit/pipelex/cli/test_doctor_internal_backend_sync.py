from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from pipelex.cli.commands.doctor_cmd import (
    ConfigLocationInfo,
    PendingMigrationsCheck,
    PendingMigrationsFinding,
    TelemetryConfigCheck,
    TelemetryConfigFinding,
    check_internal_backend_sync,
    display_health_report,
)
from pipelex.cogt.models import deck_manifest
from pipelex.cogt.models.deck_manifest import DeckFileStatus, DeckSyncReport, KitManagedArea, compute_kit_manifest, write_manifest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

CLEAN_DECK = DeckSyncReport(kit_version="1.2.0", installed_kit_version="1.2.0", manifest_present=True, files={})


class TestDoctorInternalBackendSync:
    @pytest.fixture
    def backends_dir(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        """A kit whose internal.toml declares the built-in engine, and an installed backends dir whose copy predates it."""
        kit_backends_dir = tmp_path / "kit-backends"
        kit_backends_dir.mkdir()
        (kit_backends_dir / "internal.toml").write_text("internal-with-reportlab", encoding="utf-8")
        (kit_backends_dir / "openai.toml").write_text("openai-kit", encoding="utf-8")
        mocker.patch.object(deck_manifest, "kit_backends_dir", return_value=kit_backends_dir)
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.2.0")
        backends_dir = tmp_path / "inference" / "backends"
        backends_dir.mkdir(parents=True)
        (backends_dir / "internal.toml").write_text("internal-before-reportlab", encoding="utf-8")
        (backends_dir / "openai.toml").write_text("openai-user", encoding="utf-8")
        return backends_dir

    def test_a_missing_backends_dir_is_healthy(self, tmp_path: Path) -> None:
        """An uninitialized directory is the config checks' to report, as it is for the deck."""
        healthy, report, message = check_internal_backend_sync(config_dir=tmp_path)

        assert healthy is True
        assert report.manifest_present is False
        assert message == "Backends directory not present"

    def test_a_stale_internal_toml_is_reported_as_drift(self, tmp_path: Path, backends_dir: Path) -> None:
        """An internal.toml from before this release has no manifest and differs from the kit: the doctor points at `pipelex update`."""
        healthy, report, message = check_internal_backend_sync(config_dir=tmp_path)

        assert healthy is False
        assert message == "backends/internal.toml manifest missing — run `pipelex update` to materialize a baseline"
        assert report.files == {"internal.toml": DeckFileStatus.LOCALLY_MODIFIED}
        assert backends_dir.is_dir()

    def test_an_internal_toml_the_kit_moved_past_is_reported_as_behind(self, tmp_path: Path, backends_dir: Path, mocker: MockerFixture) -> None:
        write_manifest(
            deck_manifest.DeckManifest(
                kit_version="1.1.0", files={"internal.toml": deck_manifest.compute_file_sha256(backends_dir / "internal.toml")}
            ),
            installed_dir=backends_dir,
        )
        mocker.patch.object(deck_manifest, "get_package_version", return_value="1.2.0")

        healthy, report, message = check_internal_backend_sync(config_dir=tmp_path)

        assert healthy is False
        assert message == "backends/internal.toml installed for pipelex 1.1.0, current is 1.2.0 (1 file(s) need action)"
        assert report.files == {"internal.toml": DeckFileStatus.CLEAN_BEHIND}

    def test_an_internal_toml_in_sync_is_healthy(self, tmp_path: Path, backends_dir: Path) -> None:
        (backends_dir / "internal.toml").write_text("internal-with-reportlab", encoding="utf-8")
        write_manifest(compute_kit_manifest(area=KitManagedArea.BACKENDS), installed_dir=backends_dir)

        healthy, report, message = check_internal_backend_sync(config_dir=tmp_path)

        assert healthy is True
        assert message == "backends/internal.toml is up to date with pipelex 1.2.0"
        assert report.files == {"internal.toml": DeckFileStatus.UP_TO_DATE}

    def test_the_report_shows_the_drift_and_names_pipelex_update(self, mocker: MockerFixture) -> None:
        console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.doctor_cmd.get_console", return_value=console)
        stale_report = DeckSyncReport(
            kit_version="1.2.0", installed_kit_version=None, manifest_present=False, files={"internal.toml": DeckFileStatus.LOCALLY_MODIFIED}
        )
        report_kwargs: dict[str, Any] = {
            "config_healthy": True,
            "config_message": "All configuration files present and valid",
            "config_missing_count": 0,
            "pending_migrations_check": PendingMigrationsCheck(
                finding=PendingMigrationsFinding.UP_TO_DATE, message="Every configuration file is at the current schema"
            ),
            "telemetry_check": TelemetryConfigCheck(finding=TelemetryConfigFinding.HEALTHY, message="Telemetry configured (mode: off)"),
            "backends_healthy": True,
            "backends_message": "All backends have valid credentials",
            "backend_credential_reports": {},
            "models_healthy": True,
            "models_message": "Models are valid",
            "backend_file_reports": {},
            "deck_healthy": True,
            "deck_message": "Deck is up to date with pipelex 1.2.0",
            "deck_report": CLEAN_DECK,
            "internal_backend_healthy": False,
            "internal_backend_message": "backends/internal.toml manifest missing — run `pipelex update` to materialize a baseline",
            "internal_backend_report": stale_report,
            "config_location": ConfigLocationInfo(
                config_dir="/work/project/.pipelex", is_project_local=True, project_root="/work/project", global_config_dir="/home/user/.pipelex"
            ),
        }

        display_health_report(**report_kwargs)

        output = console.export_text()
        assert "Issues Found" in output
        assert "backends/internal.toml manifest missing" in output
        assert "internal.toml — locally modified" in output
        assert "pipelex update to refresh the model deck and backends/internal.toml" in output
