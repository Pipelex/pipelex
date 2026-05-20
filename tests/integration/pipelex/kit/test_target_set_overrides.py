"""Integration tests for per-target agent rule set overrides."""

from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import build_merged_rules

PYTHON_STANDARDS_HEADING = "## Coding Standards & Best Practices for Python Code"
PYTEST_STANDARDS_HEADING_LOWER = "## writing tests"
TDD_HEADING_LOWER = "## test-driven development"


class TestTargetSetOverrides:
    def test_claude_default_set_is_lean(self):
        idx = load_index()
        claude_target = idx.agent_rules.targets["claude"]

        assert claude_target.sets is not None
        merged = build_merged_rules(idx, agent_set="all", file_list=claude_target.sets["all"])

        assert PYTHON_STANDARDS_HEADING not in merged
        assert PYTEST_STANDARDS_HEADING_LOWER not in merged.lower()
        assert TDD_HEADING_LOWER not in merged.lower()

    def test_claude_standalone_set_includes_python_and_pytest(self):
        idx = load_index()
        claude_target = idx.agent_rules.targets["claude"]

        assert claude_target.sets is not None
        merged = build_merged_rules(idx, agent_set="standalone", file_list=claude_target.sets["standalone"])

        assert PYTHON_STANDARDS_HEADING in merged
        assert "writing tests" in merged.lower()
        assert TDD_HEADING_LOWER not in merged.lower()

    def test_agents_set_keeps_python_and_pytest_without_tdd(self):
        idx = load_index()
        agents_target = idx.agent_rules.targets["agents"]

        assert agents_target.sets is not None
        merged = build_merged_rules(idx, agent_set="all", file_list=agents_target.sets["all"])

        assert PYTHON_STANDARDS_HEADING in merged
        assert "writing tests" in merged.lower()
        assert TDD_HEADING_LOWER not in merged.lower()

    def test_global_all_set_no_longer_includes_tdd(self):
        idx = load_index()

        assert "tdd.md" not in idx.agent_rules.sets["all"]
        merged = build_merged_rules(idx, agent_set="all")
        assert TDD_HEADING_LOWER not in merged.lower()
