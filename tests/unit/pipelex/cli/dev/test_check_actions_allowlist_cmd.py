from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_actions_allowlist_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.actions_allowlist_exceptions import ActionsAllowlistGuardError
from pipelex.cli.dev_cli.commands.actions_allowlist_guard import REMEDY, ActionsAllowlistViolation
from pipelex.cli.dev_cli.commands.check_actions_allowlist_cmd import check_actions_allowlist_cmd

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

#: Wide enough that no assertion below depends on where Rich decides to wrap.
CONSOLE_WIDTH = 400

VIOLATION = ActionsAllowlistViolation(
    relative_path=".github/workflows/publish-docker-hub.yml",
    lineno=226,
    reference="peter-evans/dockerhub-description@1b9a80c056b620d92cedb9d9b5a223409c68ddfa",
    detail="is not created by GitHub, not owned by the enterprise, and matched by no pattern of the policy",
)


class TestCheckActionsAllowlistCmd:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route every `get_console()` call in the command module to one StringIO-backed console."""
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH))
        return buffer

    @pytest.mark.parametrize(
        ("quiet", "expected_verdict"),
        [
            (True, "Actions allowlist check: PASSED"),
            (False, "Actions Allowlist Check: PASSED"),
        ],
    )
    def test_a_clean_tree_passes(self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool, expected_verdict: str) -> None:
        """A clean tree returns normally, which is exit 0, and a quiet run says so in one line."""
        mocker.patch.object(cmd_mod, "collect_violations", return_value=[])
        check_actions_allowlist_cmd(quiet=quiet)
        output = console_buffer.getvalue()
        assert expected_verdict in output
        if quiet:
            assert output.strip().splitlines() == [f"✓ {expected_verdict}"]

    @pytest.mark.parametrize("quiet", [True, False])
    def test_a_refused_action_exits_1_with_its_site_and_the_remedy(self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool) -> None:
        """The gate: any refused action is exit 1, and a quiet CI run still carries the site, the reference and the remedy."""
        mocker.patch.object(cmd_mod, "collect_violations", return_value=[VIOLATION])

        with pytest.raises(SystemExit) as exit_info:
            check_actions_allowlist_cmd(quiet=quiet)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert ".github/workflows/publish-docker-hub.yml:226" in output
        assert VIOLATION.reference in output
        assert REMEDY in output

    @pytest.mark.parametrize("quiet", [True, False])
    def test_a_guard_error_exits_1_with_its_message(self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool) -> None:
        """A missing or malformed allowlist fails loudly, whatever the verbosity, rather than passing."""
        mocker.patch.object(cmd_mod, "collect_violations", side_effect=ActionsAllowlistGuardError("the Actions allowlist was not found"))

        with pytest.raises(SystemExit) as exit_info:
            check_actions_allowlist_cmd(quiet=quiet)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "Actions allowlist check: FAILED" in output
        assert "the Actions allowlist was not found" in output
