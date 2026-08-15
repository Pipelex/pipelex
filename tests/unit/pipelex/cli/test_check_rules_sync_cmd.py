"""Unit tests for the check_rules_sync_cmd helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.check_rules_sync_cmd import (
    _DEFAULT_TARGETS,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _get_preferred_targets_from_toml,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    check_rules_sync_cmd,
)
from pipelex.system.configuration.configs import AgentTarget

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestGetPreferredTargetsFromToml:
    def test_default_includes_claude_and_agents(self) -> None:
        """Fallback must match pipelex.toml default of ['claude', 'agents']."""
        assert _DEFAULT_TARGETS == [AgentTarget.CLAUDE, AgentTarget.AGENTS]

    def test_returns_default_when_toml_missing(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch("pipelex.cli.dev_cli.commands.check_rules_sync_cmd.Path", return_value=tmp_path / "missing.toml")
        result = _get_preferred_targets_from_toml()
        assert result == _DEFAULT_TARGETS

    @pytest.mark.parametrize(
        ("toml_body", "expected"),
        [
            (
                '[kit]\npreferred_agent_targets = ["claude", "agents"]\n',
                [AgentTarget.CLAUDE, AgentTarget.AGENTS],
            ),
            (
                '[kit]\npreferred_agent_targets = ["cursor"]\n',
                [AgentTarget.CURSOR],
            ),
            # Empty list must NOT silently disable the sync check —
            # it should fall back to defaults.
            ("[kit]\npreferred_agent_targets = []\n", _DEFAULT_TARGETS),
            # Unknown value triggers ValueError → fallback.
            ('[kit]\npreferred_agent_targets = ["unknown"]\n', _DEFAULT_TARGETS),
            # Missing key triggers KeyError → fallback.
            ("[kit]\n", _DEFAULT_TARGETS),
        ],
    )
    def test_parses_toml_targets_with_safe_fallbacks(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        toml_body: str,
        expected: list[AgentTarget],
    ) -> None:
        pipelex_dir = tmp_path / "pipelex"
        pipelex_dir.mkdir()
        (pipelex_dir / "pipelex.toml").write_text(toml_body, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = _get_preferred_targets_from_toml()
        assert result == expected


class TestCheckRulesSyncCmdCursorExclusivity:
    """The CURSOR shortcut must require exclusivity, not membership.

    A mixed list like ['cursor', 'claude'] should NOT skip the sync check —
    it would silently bypass verification of file-based targets.
    """

    def test_cursor_only_skips(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.cli.dev_cli.commands.check_rules_sync_cmd._get_preferred_targets_from_toml",
            return_value=[AgentTarget.CURSOR],
        )
        load_index_mock = mocker.patch("pipelex.cli.dev_cli.commands.check_rules_sync_cmd.load_index")
        check_rules_sync_cmd(show_diff=False, quiet=True)
        load_index_mock.assert_called_once()

    def test_mixed_cursor_with_claude_does_not_skip(self, mocker: MockerFixture) -> None:
        """If the TOML somehow contains a mixed list, the cursor branch must NOT trigger.

        The pydantic validator forbids the mix, but this command bypasses pydantic.
        """
        mocker.patch(
            "pipelex.cli.dev_cli.commands.check_rules_sync_cmd._get_preferred_targets_from_toml",
            return_value=[AgentTarget.CURSOR, AgentTarget.CLAUDE],
        )
        # Use a fake index with a CLAUDE target that points to a path we control.
        fake_target = mocker.MagicMock()
        fake_target.path = "/nonexistent/CLAUDE.md"
        fake_target.sets = None
        fake_index = mocker.MagicMock()
        fake_index.agent_rules.targets = {AgentTarget.CLAUDE: fake_target}
        mocker.patch(
            "pipelex.cli.dev_cli.commands.check_rules_sync_cmd.load_index",
            return_value=fake_index,
        )
        mocker.patch(
            "pipelex.cli.dev_cli.commands.check_rules_sync_cmd.build_merged_rules",
            return_value="",
        )
        # Mixed cursor + claude is invalid → command should exit(1), not silently skip.
        with pytest.raises(SystemExit) as exc_info:
            check_rules_sync_cmd(show_diff=False, quiet=True)
        assert exc_info.value.code == 1
