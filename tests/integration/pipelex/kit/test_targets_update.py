from pathlib import Path

from pipelex.kit.index_loader import load_index
from pipelex.kit.markers import find_span
from pipelex.kit.targets_update import build_merged_rules, update_targets


class TestTargetsUpdate:
    """Test target file updating functionality."""

    def test_update_targets_dry_run(self, tmp_path: Path):
        """Test updating targets in dry-run mode."""
        idx = load_index()

        # Create a temporary repo root with a target file
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        target_file.write_text("# Test\n\nOriginal content\n", encoding="utf-8")

        merged_rules = build_merged_rules(idx)

        # Create a test target
        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        original_content = target_file.read_text(encoding="utf-8")

        # Dry run should not modify file
        update_targets(repo_root, merged_rules, test_targets, dry_run=True, diff=False, backup=None)

        assert target_file.read_text(encoding="utf-8") == original_content

    def test_update_targets_inserts_with_markers(self, tmp_path: Path):
        """Test that update_targets inserts content with markers."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        target_file.write_text("# Test\n\nOriginal content\n", encoding="utf-8")

        merged_rules = build_merged_rules(idx)

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        update_targets(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)

        updated_content = target_file.read_text(encoding="utf-8")
        target = test_targets["test"]

        # Verify markers are present
        assert target.marker_begin in updated_content
        assert target.marker_end in updated_content

        # Verify content is between markers
        span = find_span(updated_content, target.marker_begin, target.marker_end)
        assert span is not None

    def test_update_targets_replaces_existing_markers(self, tmp_path: Path):
        """Test that update_targets replaces content between existing markers."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"

        # Create file with existing markers
        marker_begin = "<!-- BEGIN_TEST -->"
        marker_end = "<!-- END_TEST -->"
        initial_content = f"# Test\n\n{marker_begin}\nOld content\n{marker_end}\n"
        target_file.write_text(initial_content, encoding="utf-8")

        merged_rules = build_merged_rules(idx)

        test_targets = {
            "test": idx.agent_rules.targets["agents"].model_copy(
                update={
                    "path": "test_target.md",
                    "marker_begin": marker_begin,
                    "marker_end": marker_end,
                }
            )
        }

        update_targets(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=None)

        updated_content = target_file.read_text(encoding="utf-8")

        # Verify markers still exist
        assert marker_begin in updated_content
        assert marker_end in updated_content

        # Verify old content is replaced
        assert "Old content" not in updated_content

    def test_update_targets_creates_backup(self, tmp_path: Path):
        """Test that update_targets creates backup files when requested."""
        idx = load_index()

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target_file = repo_root / "test_target.md"
        original_content = "# Test\n\nOriginal content\n"
        target_file.write_text(original_content, encoding="utf-8")

        merged_rules = build_merged_rules(idx)

        test_targets = {"test": idx.agent_rules.targets["agents"].model_copy(update={"path": "test_target.md"})}

        update_targets(repo_root, merged_rules, test_targets, dry_run=False, diff=False, backup=".bak")

        # Verify backup exists
        backup_file = target_file.with_suffix(target_file.suffix + ".bak")
        assert backup_file.exists()
        assert backup_file.read_text(encoding="utf-8") == original_content
