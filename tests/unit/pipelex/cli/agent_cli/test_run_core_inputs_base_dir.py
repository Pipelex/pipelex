"""Wiring tests: the agent CLI's local run core forwards ``inputs_base_dir`` to the runner
constructor (D3), so bare relative file paths in a loaded inputs file resolve against the
file's directory inside the shaper.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

RUN_CORE_MODULE = "pipelex.cli.agent_cli.commands.run._run_core"


class TestRunCoreInputsBaseDir:
    @pytest.fixture
    def config_mock(self, mocker: MockerFixture) -> Any:
        fake_config = mocker.MagicMock()
        fake_config.interpreter.pipeline_execution.with_execution_overrides.return_value = mocker.MagicMock()
        mocker.patch(f"{RUN_CORE_MODULE}.get_config", return_value=fake_config)
        return fake_config

    def _mock_runner_class(self, mocker: MockerFixture) -> Any:
        """Patch the protocol runner; execute() raises so the test stops right after construction."""
        runner_mock = mocker.MagicMock()
        runner_mock.execute = mocker.AsyncMock(side_effect=PipelexError("stop after construction"))
        return mocker.patch(f"{RUN_CORE_MODULE}.PipelexMTHDSProtocol", return_value=runner_mock)

    @pytest.mark.usefixtures("config_mock")
    def test_inputs_base_dir_forwarded_to_runner(self, mocker: MockerFixture, tmp_path: Path) -> None:
        runner_class_mock = self._mock_runner_class(mocker)

        with pytest.raises(PipelexError, match="stop after construction"):
            asyncio.run(
                run_pipeline_core(
                    "some_pipe",
                    inputs={"photo": "photo.jpg"},
                    dry_run=True,
                    inputs_base_dir=tmp_path,
                )
            )

        assert runner_class_mock.call_args.kwargs["inputs_base_dir"] == tmp_path

    @pytest.mark.usefixtures("config_mock")
    def test_inputs_base_dir_defaults_to_none(self, mocker: MockerFixture) -> None:
        runner_class_mock = self._mock_runner_class(mocker)

        with pytest.raises(PipelexError, match="stop after construction"):
            asyncio.run(run_pipeline_core("some_pipe", inputs={"topic": "cats"}, dry_run=True))

        assert runner_class_mock.call_args.kwargs["inputs_base_dir"] is None
