from pathlib import Path

from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import update_single_file_agent_rules


class TestUpdateSingleFileAgentRules:
    def test_update_single_file_agent_rules_dry_run(self, tmp_path: Path, agent_set: str):
        """Test that dry run does not modify files."""
        idx = load_index()

        # Create a temporary repo root with a target file
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        target_file.write_text("# Test\n\nOriginal content\n", encoding="utf-8")

        # Create a test target
        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        original_content = target_file.read_text(encoding="utf-8")

        # Dry run should not modify file
        update_single_file_agent_rules(
            repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets, dry_run=True, diff=False, backup=None
        )

        assert target_file.read_text(encoding="utf-8") == original_content

    def test_update_single_file_agent_rules_writes_content(self, tmp_path: Path, agent_set: str):
        """Test that agent rules update writes content with heading."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        target_file.write_text("# Test\n\nOriginal content\n", encoding="utf-8")

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        update_single_file_agent_rules(
            repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets, dry_run=False, diff=False, backup=None
        )

        updated_content = target_file.read_text(encoding="utf-8")

        # Verify heading is present
        assert updated_content.startswith("# Pipelex Coding Rules\n\n")

        # Verify original content is NOT preserved (file is replaced entirely)
        assert "Original content" not in updated_content

    def test_update_single_file_agent_rules_creates_backup(self, tmp_path: Path, agent_set: str):
        """Test that agent rules update creates backup files when requested."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        original_content = "# Test\n\nOriginal content\n"
        target_file.write_text(original_content, encoding="utf-8")

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        update_single_file_agent_rules(
            repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets, dry_run=False, diff=False, backup=".bak"
        )

        # Verify backup exists
        backup_file = target_file.with_suffix(target_file.suffix + ".bak")
        assert backup_file.exists()
        assert backup_file.read_text(encoding="utf-8") == original_content
