"""Test idempotency of single-file agent rules generation."""

from pathlib import Path

from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import update_single_file_agent_rules


class TestIdempotency:
    def test_update_single_file_agent_rules_is_idempotent_empty_file(self, tmp_path: Path, agent_set: str):
        """Test that running update twice on an empty file produces identical results."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"

        # Start with empty file
        target_file.write_text("", encoding="utf-8")

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        # First update
        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)
        first_result = target_file.read_text(encoding="utf-8")

        # Second update (should be identical)
        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)
        second_result = target_file.read_text(encoding="utf-8")

        # Third update (should also be identical)
        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)
        third_result = target_file.read_text(encoding="utf-8")

        assert first_result == second_result, "Second run produced different output than first run"
        assert second_result == third_result, "Third run produced different output than second run"

    def test_update_single_file_agent_rules_is_idempotent_existing_file(self, tmp_path: Path, agent_set: str):
        """Test that running update twice on a file with existing content produces identical results."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"

        # Start with file that has content
        target_file.write_text("Some existing content.\n", encoding="utf-8")

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        # First update
        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)
        first_result = target_file.read_text(encoding="utf-8")

        # Second update (should be identical)
        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)
        second_result = target_file.read_text(encoding="utf-8")

        # Third update (should also be identical)
        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)
        third_result = target_file.read_text(encoding="utf-8")

        assert first_result == second_result, "Second run produced different output than first run"
        assert second_result == third_result, "Third run produced different output than second run"

        # Verify heading is present
        assert first_result.startswith("# Pipelex Coding Rules\n\n")
