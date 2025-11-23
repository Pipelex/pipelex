"""Test idempotency of single-file agent rules generation."""

from pathlib import Path

from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import build_merged_rules, update_single_file_agent_rules


class TestIdempotency:
    def test_update_single_file_agent_rules_is_idempotent_empty_file(self, tmp_path: Path, agent_set: str):
        """Test that running update twice on an empty file produces identical results."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"

        # Start with empty file
        target_file.write_text("", encoding="utf-8")

        merged_rules = build_merged_rules(idx, agent_set=agent_set)

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        # First update
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        first_result = target_file.read_text(encoding="utf-8")

        # Second update (should be identical)
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        second_result = target_file.read_text(encoding="utf-8")

        # Third update (should also be identical)
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        third_result = target_file.read_text(encoding="utf-8")

        assert first_result == second_result, "Second run produced different output than first run"
        assert second_result == third_result, "Third run produced different output than second run"

    def test_update_single_file_agent_rules_is_idempotent_file_without_h1(self, tmp_path: Path, agent_set: str):
        """Test that running update twice on a file without H1 produces identical results."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"

        # Start with file that has content but no H1
        target_file.write_text("Some existing content without heading.\n", encoding="utf-8")

        merged_rules = build_merged_rules(idx, agent_set=agent_set)

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        # First update
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        first_result = target_file.read_text(encoding="utf-8")

        # Second update (should be identical)
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        second_result = target_file.read_text(encoding="utf-8")

        # Third update (should also be identical)
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        third_result = target_file.read_text(encoding="utf-8")

        assert first_result == second_result, "Second run produced different output than first run"
        assert second_result == third_result, "Third run produced different output than second run"

    def test_update_single_file_agent_rules_is_idempotent_file_with_h1(self, tmp_path: Path, agent_set: str):
        """Test that running update twice on a file with existing H1 produces identical results without duplicate headings."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"

        # Start with file that has an H1 heading already
        target_file.write_text("# My Existing Heading\n\nSome existing content.\n", encoding="utf-8")

        merged_rules = build_merged_rules(idx, agent_set=agent_set)

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        # First update
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        first_result = target_file.read_text(encoding="utf-8")

        # Verify no heading_1 was added inside markers (since file already has H1)
        assert first_result.count("# Pipelex Coding Rules") == 0, "Should not add heading_1 when file already has H1"
        assert first_result.count("# My Existing Heading") == 1, "Original H1 should be preserved"

        # Second update (should be identical)
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        second_result = target_file.read_text(encoding="utf-8")

        # Third update (should also be identical)
        update_single_file_agent_rules(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)
        third_result = target_file.read_text(encoding="utf-8")

        assert first_result == second_result, "Second run produced different output than first run"
        assert second_result == third_result, "Third run produced different output than second run"
