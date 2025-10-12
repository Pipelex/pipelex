from pathlib import Path

from pipelex.kit.cursor_export import export_cursor_rules
from pipelex.kit.index_loader import load_index
from pipelex.kit.paths import get_agents_dir


class TestCursorExport:
    """Test Cursor rules export functionality."""

    def test_export_cursor_rules_dry_run(self, tmp_path: Path):
        """Test Cursor export in dry-run mode."""
        idx = load_index()
        agents_dir = get_agents_dir()
        out_dir = tmp_path / "cursor_rules"

        # Dry run should not create files
        export_cursor_rules(agents_dir, out_dir, idx, dry_run=True)
        assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0

    def test_export_cursor_rules_creates_mdc_files(self, tmp_path: Path):
        """Test that Cursor export creates .mdc files."""
        idx = load_index()
        agents_dir = get_agents_dir()
        out_dir = tmp_path / "cursor_rules"

        export_cursor_rules(agents_dir, out_dir, idx, dry_run=False)

        # Verify output directory exists and contains .mdc files
        assert out_dir.exists()
        mdc_files = list(out_dir.glob("*.mdc"))
        assert len(mdc_files) > 0, "Expected .mdc files to be created"

    def test_export_cursor_rules_have_front_matter(self, tmp_path: Path):
        """Test that exported .mdc files have YAML front-matter."""
        idx = load_index()
        agents_dir = get_agents_dir()
        out_dir = tmp_path / "cursor_rules"

        export_cursor_rules(agents_dir, out_dir, idx, dry_run=False)

        # Check first .mdc file for front-matter
        mdc_files = list(out_dir.glob("*.mdc"))
        if mdc_files:
            content = mdc_files[0].read_text(encoding="utf-8")
            assert content.startswith("---\n"), "Expected YAML front-matter to start with ---"
            assert "---\n" in content[4:], "Expected YAML front-matter to end with ---"
