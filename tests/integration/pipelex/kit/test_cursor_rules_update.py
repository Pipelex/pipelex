from pathlib import Path

import pytest

from pipelex.kit.cursor_rules import update_cursor_rules
from pipelex.kit.exceptions import KitError
from pipelex.kit.index_loader import load_index


class TestUpdateCursorRules:
    def test_update_cursor_rules_creates_mdc_files(self, tmp_path: Path, agent_set: str):
        kit_index = load_index()
        repo_root = tmp_path

        update_cursor_rules(repo_root, kit_index=kit_index, agent_set=agent_set)

        cursor_rules_dir = repo_root / ".cursor" / "rules"
        assert cursor_rules_dir.exists()
        mdc_files = list(cursor_rules_dir.glob("*.mdc"))
        assert len(mdc_files) > 0, "Expected .mdc files to be created"

    def test_update_cursor_rules_have_front_matter(self, tmp_path: Path, agent_set: str):
        kit_index = load_index()
        repo_root = tmp_path

        update_cursor_rules(repo_root, kit_index=kit_index, agent_set=agent_set)

        # Check first .mdc file for front-matter
        cursor_rules_dir = repo_root / ".cursor" / "rules"
        mdc_files = list(cursor_rules_dir.glob("*.mdc"))
        if mdc_files:
            content = mdc_files[0].read_text(encoding="utf-8")
            assert content.startswith("---\n"), "Expected YAML front-matter to start with ---"
            assert "---\n" in content[4:], "Expected YAML front-matter to end with ---"

    def test_update_cursor_rules_with_agent_set(self, tmp_path: Path, agent_set: str):
        kit_index = load_index()
        repo_root = tmp_path

        update_cursor_rules(repo_root, kit_index=kit_index, agent_set=agent_set)

        cursor_rules_dir = repo_root / ".cursor" / "rules"
        exported_files: set[str] = set()
        exported_files.update(mdc_file.name for mdc_file in cursor_rules_dir.glob("*.mdc"))

        expected_files: set[str] = set()
        expected_files.update(f"{file_name.removesuffix('.md')}.mdc" for file_name in kit_index.agent_rules.sets[agent_set])

        assert exported_files == expected_files

    def test_update_cursor_rules_invalid_agent_set(self, tmp_path: Path):
        kit_index = load_index()

        with pytest.raises(KitError, match=r"Agent set 'unknown' not found in index.toml"):
            update_cursor_rules(tmp_path, kit_index=kit_index, agent_set="unknown")
