"""`pipelex init` asks where runs execute, the hosted Pipelex API listed first and taken by Enter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.init.setup_path import DEFAULT_SETUP_PATH, SetupPath
from pipelex.cli.commands.init.ui.setup_path_ui import SETUP_PATH_QUESTION, prompt_setup_path

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from tests.helpers.recorded_console import RecordedConsole


class TestSetupPathPrompt:
    def test_hosted_is_the_default(self) -> None:
        assert DEFAULT_SETUP_PATH == SetupPath.HOSTED

    def test_enter_takes_the_hosted_api_listed_first(self, mocker: MockerFixture, recorded_console: RecordedConsole) -> None:
        def press_enter(*_args: object, default: str, **_kwargs: object) -> str:
            return default

        prompt = mocker.patch("pipelex.cli.commands.init.ui.setup_path_ui.Prompt.ask", side_effect=press_enter)

        assert prompt_setup_path(console=recorded_console.console) == SetupPath.HOSTED

        assert prompt.call_args.kwargs["default"] == "1"
        shown = recorded_console.text()
        assert SETUP_PATH_QUESTION in shown
        assert shown.index("On the hosted Pipelex API, with a Pipelex API key") < shown.index("On this machine, with your own provider keys")

    @pytest.mark.parametrize(
        ("answer", "expected"),
        [("", SetupPath.HOSTED), ("1", SetupPath.HOSTED), ("2", SetupPath.LOCAL), ("local", SetupPath.LOCAL), (" Hosted ", SetupPath.HOSTED)],
    )
    def test_a_number_or_a_name_picks_the_path(
        self, mocker: MockerFixture, recorded_console: RecordedConsole, answer: str, expected: SetupPath
    ) -> None:
        mocker.patch("pipelex.cli.commands.init.ui.setup_path_ui.Prompt.ask", return_value=answer)

        assert prompt_setup_path(console=recorded_console.console) == expected

    def test_anything_else_asks_again(self, mocker: MockerFixture, recorded_console: RecordedConsole) -> None:
        prompt = mocker.patch("pipelex.cli.commands.init.ui.setup_path_ui.Prompt.ask", side_effect=["3", "[bold]x", "2"])

        assert prompt_setup_path(console=recorded_console.console) == SetupPath.LOCAL

        assert prompt.call_count == 3
        assert "Invalid choice" in recorded_console.text()
