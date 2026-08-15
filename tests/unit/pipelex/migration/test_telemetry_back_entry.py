"""The one migration the package ships today, exercised on the shape it is about.

Everything else about migration behaviour is tested against synthetic surfaces, deliberately. This
module is the exception the entry earns: `telemetry-config@2` is about a real file that real users
still have, and what it must do to that file cannot be asked of a stand-in.

Two hardcoded sniffs still tell such a user to re-initialize their `telemetry.toml` — `doctor`'s
telemetry row and the telemetry validation error handler — which throws away every choice they
made. What is asserted here is what replaces them: the ledger carries a flat file onto the current
shape, keeping the values, and produces something the model accepts.
"""

from typing import Any

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import load_ledger
from pipelex.migration.surfaces import packaged_migration_dir
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig
from pipelex.tools.misc.toml_utils import load_toml_from_content

SURFACE_ID = "telemetry-config"


class TestTheTelemetryBackEntry:
    def _old_shape_document(self) -> str:
        """The hand-authored `before@2.toml` — the flat shape, as the entry's own check reads it."""
        path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID, schema_version=2)
        return path.read_text(encoding="utf-8")

    def test_replaying_the_ledger_over_a_flat_file_produces_a_document_the_model_accepts(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=self._old_shape_document())

        assert [step.entry_id for step in replay.steps] == ["telemetry-config@2"]
        assert replay.blocked == []

        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        assert TelemetryConfig.model_validate(migrated).custom_posthog.mode is PostHogMode.ANONYMOUS
        assert migrated["custom_posthog"]["api_key"] == "phc_example_project_api_key"
        assert "telemetry_mode" not in migrated

    def test_replaying_it_again_changes_nothing(self) -> None:
        """The migrated file is a current file, and a current file is what replay must not touch."""
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)
        once = replay_ledger_over_text(ledger=ledger, text=self._old_shape_document())
        twice = replay_ledger_over_text(ledger=ledger, text=once.text)
        assert twice.steps == []
        assert twice.text is once.text
