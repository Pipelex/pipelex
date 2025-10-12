"""Integration tests for building merged agent documentation."""

import pytest

from pipelex.kit.index_loader import load_index
from pipelex.kit.paths import get_agents_dir
from pipelex.kit.targets_update import build_merged_rules


class TestMergedRules:
    """Test building merged agent documentation."""

    def test_build_merged_rules_default_set(self):
        """Test building merged rules with default set."""
        idx = load_index()
        agents_dir = get_agents_dir()

        merged = build_merged_rules(agents_dir, idx)
        assert merged is not None
        assert len(merged) > 0
        assert merged.endswith("\n")

    def test_build_merged_rules_specific_set(self):
        """Test building merged rules with specific set."""
        idx = load_index()
        agents_dir = get_agents_dir()

        # Test with 'all' set
        merged = build_merged_rules(agents_dir, idx, agent_set="all")
        assert merged is not None
        assert len(merged) > 0

    def test_build_merged_rules_invalid_set(self):
        """Test building merged rules with invalid set name."""
        idx = load_index()
        agents_dir = get_agents_dir()

        with pytest.raises(ValueError, match="Agent set 'nonexistent' not found"):
            build_merged_rules(agents_dir, idx, agent_set="nonexistent")

    def test_merged_rules_contain_demoted_headings(self):
        """Test that merged rules have demoted headings."""
        idx = load_index()
        agents_dir = get_agents_dir()

        merged = build_merged_rules(agents_dir, idx)

        # If demote is 1, check that we have ## headings (demoted from #)
        if idx.agent_rules.demote > 0:
            assert "##" in merged, "Expected demoted headings in merged content"
