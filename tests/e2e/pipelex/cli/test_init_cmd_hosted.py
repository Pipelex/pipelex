"""`pipelex init` on the hosted path: Enter takes it, the kit's inference files stay as written, and a key is obtained or kept."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.setup_path import SetupPath, write_run_execution
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.login.command import LoginOutcome
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir
from tests.helpers.init_cmd_helpers import MockedInitEnvironment

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _printed(env: MockedInitEnvironment) -> str:
    return "\n".join(str(call.args[0]) for call in env.mock_console.print.call_args_list if call.args)


def _assert_kit_inference_files(env: MockedInitEnvironment) -> None:
    kit_inference_dir = get_kit_configs_dir() / "inference"
    for name in ("backends.toml", "routing_profiles.toml"):
        assert (env.inference_dir / name).read_text(encoding="utf-8") == (kit_inference_dir / name).read_text(encoding="utf-8")


class TestInitHostedPath:
    def test_enter_takes_the_hosted_api_and_signs_in(self, tmp_path: Path, mocker: MockerFixture) -> None:
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input("")  # Where runs execute: Enter, the hosted Pipelex API
        env.setup_mocks()
        credentials = mocker.patch("pipelex.cli.commands.init.command.prompt_credentials")

        init_cmd(focus=InitFocus.ALL)

        env.verify_run_execution(RunExecution.HOSTED)
        _assert_kit_inference_files(env)
        env.verify_file_exists("telemetry.toml")
        env.mock_login.assert_called_once()
        credentials.assert_not_called()
        assert env.prompt_inputs == []

    def test_a_key_already_set_skips_the_login(self, tmp_path: Path, mocker: MockerFixture) -> None:
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()
        env.add_confirm_input(True)
        env.choose_setup_path(SetupPath.HOSTED)
        env.setup_mocks()
        os.environ[PIPELEX_API_KEY_ENV_KEY] = "plx_sk_test_not_a_secret"

        init_cmd(focus=InitFocus.ALL)

        env.verify_run_execution(RunExecution.HOSTED)
        env.mock_login.assert_not_called()
        env.mock_browser_open.assert_not_called()
        assert "already set" in _printed(env)

    def test_a_failed_login_keeps_the_setup_and_names_pipelex_login(self, tmp_path: Path, mocker: MockerFixture) -> None:
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()
        env.add_confirm_input(True)
        env.choose_setup_path(SetupPath.HOSTED)
        env.setup_mocks()
        env.mock_login.return_value = LoginOutcome.NO_KEY

        init_cmd(focus=InitFocus.ALL)

        env.verify_run_execution(RunExecution.HOSTED)
        env.verify_file_exists("telemetry.toml")
        assert "pipelex login" in _printed(env)

    def test_doctor_fix_takes_the_hosted_default_without_asking_or_opening_a_browser(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`pipelex doctor --fix` installs missing configuration files this way: nobody is there to answer."""
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()
        env.setup_mocks()

        init_cmd(focus=InitFocus.CONFIG, skip_confirmation=True)

        env.verify_run_execution(RunExecution.HOSTED)
        _assert_kit_inference_files(env)
        env.mock_prompt_ask.assert_not_called()
        env.mock_confirm_ask.assert_not_called()
        env.mock_login.assert_not_called()
        env.mock_browser_open.assert_not_called()
        assert "Run [cyan]pipelex login[/cyan]" in _printed(env)

    def test_a_config_reset_keeps_hosted_runs_and_asks_for_no_provider_key(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`pipelex init config` on an existing setup resets pipelex.toml without asking again, so it keeps the answer."""
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)
        write_run_execution(pipelex_toml_path=env.pipelex_dir / "pipelex.toml", execution=RunExecution.HOSTED)
        env.add_confirm_input(True)
        env.setup_mocks()
        credentials = mocker.patch("pipelex.cli.commands.init.command.prompt_credentials")

        init_cmd(focus=InitFocus.CONFIG)

        env.verify_run_execution(RunExecution.HOSTED)
        credentials.assert_not_called()
        env.mock_login.assert_not_called()
        env.mock_prompt_ask.assert_not_called()

    def test_init_inference_configures_this_machine_without_the_question(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`pipelex init inference` sets up the local backends on purpose and leaves where runs execute as it is."""
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)
        write_run_execution(pipelex_toml_path=env.pipelex_dir / "pipelex.toml", execution=RunExecution.HOSTED)
        env.add_confirm_input(True)
        env.add_prompt_input("")  # Backend selection: the recommended default, not the setup question
        env.setup_mocks()

        init_cmd(focus=InitFocus.INFERENCE)

        env.verify_run_execution(RunExecution.HOSTED)
        env.mock_login.assert_not_called()
        assert env.prompt_inputs == []
