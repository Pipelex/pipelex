from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core  # pyright: ignore[reportPrivateUsage]
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd as agent_run_method_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.methods.fetching import MethodProvenance

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

HUMAN_RUN_METHOD_MODULE = "pipelex.cli.commands.run.method_cmd"
AGENT_RUN_METHOD_MODULE = "pipelex.cli.agent_cli.commands.run.method_cmd"
AGENT_RUN_CORE_MODULE = "pipelex.cli.agent_cli.commands.run._run_core"

PACKAGE_ADDRESS = "github.com/acme/methods/invoices"


def _method_mock(*, mocker: MockerFixture, method_dir: Path, is_published: bool) -> Any:
    method_mock = mocker.MagicMock()
    method_mock.mthds_files = []
    method_mock.path = method_dir
    method_mock.provenance = MethodProvenance(address=PACKAGE_ADDRESS, tag="v1.0.0", commit_sha="0" * 40) if is_published else None
    return method_mock


class TestRunMethodAddress:
    @pytest.fixture
    def tty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make stdin look like a TTY so the agent CLI's input parsing skips its stdin fallback."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    @pytest.mark.parametrize(("is_published", "expected_address"), [(True, PACKAGE_ADDRESS), (False, None)])
    def test_the_human_cli_hands_the_package_address_to_the_run(
        self, mocker: MockerFixture, tmp_path: Path, is_published: bool, expected_address: str | None
    ) -> None:
        """The package address is the method's identity behind each `pipe_id` when the run names no `method_id`."""
        mocker.patch(
            f"{HUMAN_RUN_METHOD_MODULE}.resolve_method_target",
            return_value=("my_pipe", [str(tmp_path)], _method_mock(mocker=mocker, method_dir=tmp_path, is_published=is_published)),
        )
        execute_run_mock = mocker.patch(f"{HUMAN_RUN_METHOD_MODULE}.execute_run")

        run_method_cmd(name=PACKAGE_ADDRESS if is_published else "my-method")

        assert execute_run_mock.call_args.kwargs["method_address"] == expected_address

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize(("is_published", "expected_address"), [(True, PACKAGE_ADDRESS), (False, None)])
    def test_the_agent_cli_hands_the_package_address_to_the_run(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], is_published: bool, expected_address: str | None
    ) -> None:
        mocker.patch(
            f"{AGENT_RUN_METHOD_MODULE}.resolve_method_target",
            return_value=("my_pipe", [str(tmp_path)], _method_mock(mocker=mocker, method_dir=tmp_path, is_published=is_published)),
        )
        mocker.patch(f"{AGENT_RUN_METHOD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{AGENT_RUN_METHOD_MODULE}.Pipelex.teardown_if_needed")
        run_core_mock = mocker.patch(f"{AGENT_RUN_METHOD_MODULE}.run_pipeline_core", new=mocker.AsyncMock(return_value={"answer": "42"}))

        agent_run_method_cmd(name=PACKAGE_ADDRESS if is_published else "my-method", output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["method_address"] == expected_address

    def test_the_agent_run_core_hands_the_address_to_the_runner(self, mocker: MockerFixture) -> None:
        fake_config = mocker.MagicMock()
        mocker.patch(f"{AGENT_RUN_CORE_MODULE}.get_config", return_value=fake_config)
        runner_mock = mocker.MagicMock()
        runner_mock.execute = mocker.AsyncMock(side_effect=PipelexError("stop after construction"))
        runner_class_mock = mocker.patch(f"{AGENT_RUN_CORE_MODULE}.PipelexMTHDSProtocol", return_value=runner_mock)

        with pytest.raises(PipelexError, match="stop after construction"):
            asyncio.run(run_pipeline_core("some_pipe", inputs={"topic": "cats"}, dry_run=True, method_address=PACKAGE_ADDRESS))

        assert runner_class_mock.call_args.kwargs["method_address"] == PACKAGE_ADDRESS
