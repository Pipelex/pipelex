"""The `inference-backend@3` entry, exercised on the file it is about.

The entry is `unsafe`: it rewrites nothing and only reports a backend file that still names the Bedrock
SDK handle `bedrock_aioboto3`. No reference document the ledger gates replay over carries that value, so
a typo in its mapping would pass every gate and the entry would go silent on the very files it exists
for. These tests hand it such a file.
"""

from pathlib import Path
from typing import Any

import pipelex
from pipelex.migration.engine import apply_ops_over_text, replay_ledger_over_text
from pipelex.migration.ledger import MigrationLedger, load_ledger, packaged_migration_dir
from pipelex.migration.plan import BlockedEntryReason
from pipelex.tools.misc.toml_utils import load_toml_from_content

SURFACE_ID = "inference-backend"
ENTRY_ID = "inference-backend@3"
KIT_BACKENDS_DIR = Path(pipelex.__file__).parent / "kit" / "configs" / "inference" / "backends"

STALE_BEDROCK_FILE = """\
[defaults]
model_type = "llm"
sdk = "bedrock_aioboto3"
structure_method = "instructor/openai_tools"

["claude-4.5-sonnet"]
model_id = "anthropic.claude-sonnet-4-5"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 3.0, output = 15.0 }
"""


def _ledger() -> MigrationLedger:
    return load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)


class TestTheBackendByHandEntry:
    def test_a_stale_file_is_reported_and_left_untouched(self) -> None:
        replay = replay_ledger_over_text(ledger=_ledger(), text=STALE_BEDROCK_FILE)

        assert replay.steps == []
        assert [blocked.entry_id for blocked in replay.blocked] == [ENTRY_ID]
        assert replay.blocked[0].reason == BlockedEntryReason.UNSAFE
        assert replay.blocked[0].guidance is not None
        assert "bedrock_aioboto" in replay.blocked[0].guidance
        assert replay.text == STALE_BEDROCK_FILE

    def test_the_operations_rewrite_the_stale_handle_to_the_current_one(self) -> None:
        """What the guidance tells the user to write is what the operations would have written."""
        entry = next(entry for entry in _ledger().migration if entry.id == ENTRY_ID)

        migrated: dict[str, Any] = load_toml_from_content(apply_ops_over_text(text=STALE_BEDROCK_FILE, ops=entry.ops).text)

        assert migrated["defaults"]["sdk"] == "bedrock_aioboto"
        assert migrated["defaults"]["structure_method"] == "instructor/openai_tools"

    def test_the_file_we_ship_is_not_reported(self) -> None:
        replay = replay_ledger_over_text(ledger=_ledger(), text=(KIT_BACKENDS_DIR / "bedrock.toml").read_text(encoding="utf-8"))

        assert replay.blocked == []
        assert replay.steps == []
