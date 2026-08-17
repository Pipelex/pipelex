"""The backend entry, exercised on the shape it is about.

`inference-backend@2` deletes `prompting_target` from every root table of a backend definition file.
Like `telemetry-config@2` beside it, it is about real files on real machines rather than about the
migration machinery, and what it must do to such a file cannot be asked of a synthetic surface: the
key sits both in `[defaults]` — where the loader's wholesale copy makes one occurrence break *every*
model of the file — and on individual models, where it is rejected by name. Both halves are fatal
today, so the assertion that matters is not "the key is gone" but "the loader now accepts what comes
out", which is what `describe_model_spec_document_rejection` answers here.

The other half of the entry's job is the one a delete is most likely to get wrong: the header-shaped
keys of a model table belong to the request, the loader never validates them, and a wildcard that
reached them would silently strip a user's routing. They are asserted present, by value.
"""

from typing import Any

from pipelex.cogt.model_backends.model_spec_document import describe_model_spec_document_rejection
from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
from pipelex.tools.misc.toml_utils import load_toml_from_content

SURFACE_ID = "inference-backend"
REMOVED_KEY = "prompting_target"


class TestTheBackendBackEntry:
    def _old_shape_document(self) -> str:
        """The hand-authored `before@2.toml` — a pre-#1104 backend file, as the entry's own check reads it."""
        path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID, schema_version=2)
        return path.read_text(encoding="utf-8")

    def test_replaying_the_ledger_over_a_stale_backend_file_produces_one_the_loader_accepts(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=self._old_shape_document())

        assert [step.entry_id for step in replay.steps] == ["inference-backend@2"]
        assert replay.blocked == []

        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        # The verdict the boot gives, not a proxy for it: `[defaults]` is merged into every model
        # table and the merge is what has to validate.
        assert describe_model_spec_document_rejection(document=migrated) is None
        # The key is gone from both the shared table and the model that overrode it, which are the
        # two occurrences the wildcard has to reach.
        assert REMOVED_KEY not in migrated["defaults"]
        assert REMOVED_KEY not in migrated["gemini-2.5-pro"]
        assert not any(REMOVED_KEY in table for table in migrated.values())

        # Nothing else moved. Stated as the whole document rather than key by key, because what this
        # entry must not do is broader than any list of keys worth naming — the header-shaped keys of
        # a model table in particular, which the loader never validates and a stray wildcard would
        # strip without anything noticing.
        assert migrated == {
            "defaults": {
                "model_type": "llm",
                "sdk": "portkey_completions",
                "structure_method": "instructor/openai_tools",
                "thinking_mode": "none",
            },
            "gpt-4o": {
                "inputs": ["text", "images", "pdf"],
                "outputs": ["text", "structured"],
                "costs": {"input": 2.5, "output": 10.0},
                "sdk": "portkey_responses",
                "structure_method": "instructor/openai_responses_tools",
                "thinking_mode": "none",
                "x-portkey-provider": "@openai",
            },
            "gemini-2.5-pro": {
                "model_id": "gemini-2.5-pro",
                "inputs": ["text", "images", "pdf"],
                "outputs": ["text", "structured"],
                "max_prompt_images": 3000,
                "costs": {"input": 1.25, "output": 10.0},
                "thinking_mode": "manual",
                "x-portkey-provider": "@google",
                "x-portkey-config": "pc-example-config-id",
            },
        }

    def test_every_line_the_entry_does_not_delete_survives_byte_for_byte(self) -> None:
        """Parsing proves the values; only the text proves the comments, the spacing and the quoting."""
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)
        before_text = self._old_shape_document()
        after_text = replay_ledger_over_text(ledger=ledger, text=before_text).text

        deleted_lines = [line for line in before_text.splitlines() if line.startswith(f"{REMOVED_KEY} =")]
        assert len(deleted_lines) == 2
        surviving_lines = [line for line in before_text.splitlines() if line not in deleted_lines]
        assert after_text.splitlines() == surviving_lines

    def test_replaying_it_again_changes_nothing(self) -> None:
        """A migrated file is a current file, and every kit backend file is already one — replay must not touch either."""
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=SURFACE_ID)
        once = replay_ledger_over_text(ledger=ledger, text=self._old_shape_document())
        twice = replay_ledger_over_text(ledger=ledger, text=once.text)
        assert twice.steps == []
        assert twice.text is once.text
