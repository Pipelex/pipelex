"""Regression tests for _sync_agent_rules cleanup behavior."""

from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.cli.dev_cli.commands import kit_cmd
from pipelex.kit.index_loader import load_index
from pipelex.system.configuration.configs import AgentTarget


class TestSyncAgentRulesCleanup:
    def test_targets_filter_does_not_shrink_cleanup_keep_set(self, tmp_path: Path, mocker: MockerFixture):
        """`--targets=claude --cleanup` must not delete AGENTS.md when both targets remain configured.

        Regression test for the bug where _sync_agent_rules overwrote `preferred_targets`
        with the `--targets` subset, causing _cleanup_other_targets to receive a narrowed
        keep-set and delete still-configured rule files.
        """
        idx = load_index()
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        agents_path = repo_root / "AGENTS.md"
        claude_path = repo_root / "CLAUDE.md"
        agents_path.write_text("# AGENTS\n", encoding="utf-8")
        claude_path.write_text("# CLAUDE\n", encoding="utf-8")

        fake_config = mocker.MagicMock()
        fake_config.pipelex.kit_config.preferred_agent_targets = [AgentTarget.CLAUDE, AgentTarget.AGENTS]
        mocker.patch.object(kit_cmd, "get_config", return_value=fake_config)

        kit_cmd._sync_agent_rules(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            repo_root=repo_root,
            agent_set="all",
            cleanup=True,
            kit_index=idx,
            targets_filter=[AgentTarget.CLAUDE],
        )

        assert agents_path.exists(), "AGENTS.md must not be deleted when 'agents' is still in preferred_agent_targets"
        assert claude_path.exists(), "CLAUDE.md must be updated, not deleted"
        assert claude_path.read_text(encoding="utf-8").startswith("# Pipelex Coding Rules"), "CLAUDE.md should have been regenerated"
