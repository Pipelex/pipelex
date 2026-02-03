from pathlib import Path

from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import update_single_file_agent_rules


class TestUpdateSingleFileAgentRules:
    def test_update_single_file_agent_rules_writes_content(self, tmp_path: Path, agent_set: str):
        """Test that agent rules update writes content with heading."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        target_file.write_text("# Test\n\nOriginal content\n", encoding="utf-8")

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        update_single_file_agent_rules(repo_root=repo_root, kit_index=idx, agent_set=agent_set, targets=test_targets)

        updated_content = target_file.read_text(encoding="utf-8")

        # Verify heading is present
        assert updated_content.startswith("# Pipelex Coding Rules\n\n")

        # Verify original content is NOT preserved (file is replaced entirely)
        assert "Original content" not in updated_content
