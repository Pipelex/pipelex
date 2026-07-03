"""Unit tests for the drift contract digest: canonical, deterministic, definition-sensitive."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.drift.core import compute_contract_digest
from pipelex.cli.dev_cli.commands.drift.models import DriftContract, load_manifest

if TYPE_CHECKING:
    from pathlib import Path

TRIGGER_FILES = {
    "pipelex/pipelex.toml": "blob:99ffee0000000000000000000000000000000000",
    "pipelex/system/configuration/configs.py": "blob:a1b2c30000000000000000000000000000000000",
}


def _contract(**overrides: object) -> DriftContract:
    fields: dict[str, object] = {
        "description": "Config docs must track the config model.",
        "triggers": ["pipelex/system/configuration/**/*.py", "pipelex/pipelex.toml"],
        "exclude": [],
        "review": ["docs/configuration/**/*.md"],
        "verify_commands": ["make tb"],
    }
    fields.update(overrides)
    return DriftContract.model_validate(fields)


class TestDriftCoreDigest:
    def test_digest_is_stable_across_runs(self) -> None:
        """The same contract and trigger files always produce the same digest."""
        digest_first = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_second = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        assert digest_first == digest_second
        assert digest_first.startswith("sha256:")

    def test_glob_list_reorder_keeps_digest(self) -> None:
        """Reordering trigger globs does not change the digest — matching is order-independent."""
        reordered = _contract(triggers=["pipelex/pipelex.toml", "pipelex/system/configuration/**/*.py"])
        digest_original = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_reordered = compute_contract_digest(reordered, contract_id="config-docs", trigger_files=TRIGGER_FILES)
        assert digest_original == digest_reordered

    def test_defaulted_exclude_equals_explicit_empty(self) -> None:
        """A contract with no `exclude` key digests identically to one with `exclude = []`."""
        defaulted = DriftContract.model_validate(
            {
                "description": "Config docs must track the config model.",
                "triggers": ["pipelex/system/configuration/**/*.py", "pipelex/pipelex.toml"],
                "review": ["docs/configuration/**/*.md"],
                "verify_commands": ["make tb"],
            }
        )
        digest_defaulted = compute_contract_digest(defaulted, contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_explicit = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        assert digest_defaulted == digest_explicit

    def test_definition_change_changes_digest(self) -> None:
        """Editing the contract definition (description, review targets) forces a re-ack."""
        digest_original = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_new_description = compute_contract_digest(_contract(description="Changed."), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_new_review = compute_contract_digest(
            _contract(review=["docs/configuration/**/*.md", "docs/other.md"]), contract_id="config-docs", trigger_files=TRIGGER_FILES
        )
        assert digest_new_description != digest_original
        assert digest_new_review != digest_original

    def test_contract_id_is_part_of_the_digest(self) -> None:
        digest_one = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_two = compute_contract_digest(_contract(), contract_id="renamed-docs", trigger_files=TRIGGER_FILES)
        assert digest_one != digest_two

    def test_verify_commands_order_is_part_of_the_definition(self) -> None:
        """verify_commands run in order, so reordering them is a definition change."""
        two_commands = _contract(verify_commands=["make tb", "make cko"])
        reordered = _contract(verify_commands=["make cko", "make tb"])
        digest_one = compute_contract_digest(two_commands, contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_two = compute_contract_digest(reordered, contract_id="config-docs", trigger_files=TRIGGER_FILES)
        assert digest_one != digest_two

    def test_trigger_file_content_change_changes_digest(self) -> None:
        changed = dict(TRIGGER_FILES)
        changed["pipelex/pipelex.toml"] = "blob:1234560000000000000000000000000000000000"
        digest_original = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_changed = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=changed)
        assert digest_original != digest_changed

    def test_trigger_file_added_or_removed_changes_digest(self) -> None:
        digest_original = compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=TRIGGER_FILES)
        grown = dict(TRIGGER_FILES)
        grown["pipelex/system/configuration/new.py"] = "blob:feedbeef00000000000000000000000000000000"
        shrunk = {"pipelex/pipelex.toml": TRIGGER_FILES["pipelex/pipelex.toml"]}
        assert compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=grown) != digest_original
        assert compute_contract_digest(_contract(), contract_id="config-docs", trigger_files=shrunk) != digest_original

    def test_manifest_reformat_and_comments_keep_digest(self, tmp_path: Path) -> None:
        """Reformatting drift.toml (whitespace, comments, glob order) must not change any digest."""
        original = tmp_path / "original"
        reformatted = tmp_path / "reformatted"
        original.mkdir()
        reformatted.mkdir()
        (original / "drift.toml").write_text(
            """
version = 1

[contracts.config-docs]
description = "Config docs must track the config model."
triggers = ["pipelex/system/configuration/**/*.py", "pipelex/pipelex.toml"]
review = ["docs/configuration/**/*.md"]
verify_commands = ["make tb"]
"""
        )
        (reformatted / "drift.toml").write_text(
            """
# Drift contracts manifest — reformatted, same meaning.
version = 1

[contracts.config-docs]
description = "Config docs must track the config model."
# glob order swapped, exclude spelled out explicitly
triggers = [
    "pipelex/pipelex.toml",
    "pipelex/system/configuration/**/*.py",
]
exclude = []
review = ["docs/configuration/**/*.md"]
verify_commands = ["make tb"]
"""
        )
        manifest_original = load_manifest(original)
        manifest_reformatted = load_manifest(reformatted)
        digest_original = compute_contract_digest(manifest_original.contracts["config-docs"], contract_id="config-docs", trigger_files=TRIGGER_FILES)
        digest_reformatted = compute_contract_digest(
            manifest_reformatted.contracts["config-docs"], contract_id="config-docs", trigger_files=TRIGGER_FILES
        )
        assert digest_original == digest_reformatted
