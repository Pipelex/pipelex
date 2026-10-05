"""The `inference-backend@4` entry, exercised on the files it is about.

The entry is `unsafe`: it rewrites nothing and only reports a backend file that still names one of the
hosted backend's former `manifold_*` SDK handles. No reference document the ledger gates replay over
carries those values, so a typo in its mapping would pass every gate and the entry would go silent on the
very files it exists for. These tests hand it such files.
"""

from typing import Any

import pytest

from pipelex.migration.engine import apply_ops_over_text, replay_ledger_over_text
from pipelex.migration.ledger import MigrationLedger, load_ledger, packaged_migration_dir
from pipelex.migration.plan import BlockedEntryReason
from pipelex.providers.pipelex_hosted.pipelex_hosted_constants import PipelexHostedSdk
from pipelex.tools.misc.toml_utils import load_toml_from_content

SURFACE_ID = "inference-backend"
ENTRY_ID = "inference-backend@4"

STALE_HOSTED_FILE = """\
[defaults]
model_type = "llm"
sdk = "manifold_completions"

["claude-4.5-sonnet"]
sdk = "manifold_anthropic"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 3.0, output = 15.0 }

["gpt-image-1"]
model_type = "img_gen"
sdk = "manifold_img_gen"
inputs = ["text"]
outputs = ["image"]
costs = { input = 5.0, output = 40.0 }
"""

# The handles the entry renames, closed at the set that shipped: a hosted sdk added later never had a
# former spelling, so it belongs in no pair here.
RENAMED_HANDLES = (
    ("manifold_anthropic", "pipelex_hosted_anthropic"),
    ("manifold_completions", "pipelex_hosted_completions"),
    ("manifold_responses", "pipelex_hosted_responses"),
    ("manifold_img_gen", "pipelex_hosted_img_gen"),
    ("manifold_extract", "pipelex_hosted_extract"),
    ("manifold_search", "pipelex_hosted_search"),
)


def _ledger() -> MigrationLedger:
    return load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)


class TestTheHostedSdkByHandEntry:
    def test_a_stale_file_is_reported_and_left_untouched(self) -> None:
        replay = replay_ledger_over_text(ledger=_ledger(), text=STALE_HOSTED_FILE)

        assert replay.steps == []
        assert [blocked.entry_id for blocked in replay.blocked] == [ENTRY_ID]
        assert replay.blocked[0].reason == BlockedEntryReason.UNSAFE
        assert replay.blocked[0].guidance is not None
        assert "pipelex_hosted" in replay.blocked[0].guidance
        assert replay.text == STALE_HOSTED_FILE

    def test_the_operations_rewrite_every_stale_handle_to_the_current_one(self) -> None:
        """What the guidance tells the user to write is what the operations would have written."""
        entry = next(entry for entry in _ledger().migration if entry.id == ENTRY_ID)

        migrated: dict[str, Any] = load_toml_from_content(apply_ops_over_text(text=STALE_HOSTED_FILE, ops=entry.ops).text)

        assert migrated["defaults"]["sdk"] == PipelexHostedSdk.COMPLETIONS
        assert migrated["claude-4.5-sonnet"]["sdk"] == PipelexHostedSdk.ANTHROPIC
        assert migrated["gpt-image-1"]["sdk"] == PipelexHostedSdk.IMG_GEN

    @pytest.mark.parametrize(("former", "current"), RENAMED_HANDLES)
    def test_every_former_handle_maps_to_its_current_one(self, former: str, current: str) -> None:
        entry = next(entry for entry in _ledger().migration if entry.id == ENTRY_ID)
        stale = f'[defaults]\nsdk = "{former}"\n'

        migrated: dict[str, Any] = load_toml_from_content(apply_ops_over_text(text=stale, ops=entry.ops).text)

        assert migrated["defaults"]["sdk"] == current

    @pytest.mark.parametrize(("former", "current"), RENAMED_HANDLES)
    def test_every_target_is_a_handle_the_plugin_registers(self, former: str, current: str) -> None:
        assert former not in set(PipelexHostedSdk)
        assert current in set(PipelexHostedSdk)
