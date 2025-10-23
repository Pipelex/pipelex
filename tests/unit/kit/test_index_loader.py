from pipelex.kit.index_loader import load_index


class TestKitIndexLoader:
    """Test kit index loading and validation."""

    def test_load_index_succeeds(self):
        """Test that index.toml loads successfully."""
        idx = load_index()
        assert idx is not None
        assert idx.agent_rules is not None
        assert idx.meta is not None

    def test_index_has_required_structure(self):
        """Test that loaded index has expected structure."""
        idx = load_index()
        assert hasattr(idx.agent_rules, "sets")
        assert hasattr(idx.agent_rules, "default_set")
        assert hasattr(idx.agent_rules, "demote")
        assert hasattr(idx.agent_rules, "cursor")
        assert hasattr(idx.agent_rules, "targets")

    def test_index_sets_contain_expected_files(self):
        """Test that agent_rules sets reference expected markdown files."""
        idx = load_index()
        assert "pipelex_language" in idx.agent_rules.sets
        assert "all" in idx.agent_rules.sets
        assert len(idx.agent_rules.sets["all"]) > 0

        # Verify files in sets end with .md
        for file_list in idx.agent_rules.sets.values():
            for file_name in file_list:
                assert file_name.endswith(".md"), f"Expected .md file, got {file_name}"

    def test_index_has_valid_default_set(self):
        """Test that default_set points to an existing set."""
        idx = load_index()
        default_set = idx.agent_rules.default_set
        assert default_set in idx.agent_rules.sets, f"Default set '{default_set}' not found in sets"
