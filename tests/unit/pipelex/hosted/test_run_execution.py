from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.config import get_config
from pipelex.hosted.execution import configured_run_execution, resolve_run_execution
from pipelex.hosted.run_config import RunConfig, RunExecution
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.configs import PipelexConfig

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

EXECUTION_MODULE = "pipelex.hosted.execution"


class TestRunExecution:
    @pytest.mark.parametrize(
        ("requested", "configured", "expected"),
        [
            (RunExecution.HOSTED, RunExecution.LOCAL, RunExecution.HOSTED),
            (RunExecution.LOCAL, RunExecution.HOSTED, RunExecution.LOCAL),
            (None, RunExecution.HOSTED, RunExecution.HOSTED),
            (None, RunExecution.LOCAL, RunExecution.LOCAL),
        ],
    )
    def test_the_flag_wins_then_the_setting(
        self,
        mocker: MockerFixture,
        requested: RunExecution | None,
        configured: RunExecution,
        expected: RunExecution,
    ) -> None:
        """A flag on the run decides; with none, the `[run] execution` setting does."""
        mocker.patch(f"{EXECUTION_MODULE}.configured_run_execution", return_value=configured)
        assert resolve_run_execution(requested=requested) is expected

    def test_a_flag_reads_no_configuration(self, mocker: MockerFixture) -> None:
        """A run that names where it executes never loads the configuration to find out."""
        reader = mocker.patch(f"{EXECUTION_MODULE}.configured_run_execution", side_effect=AssertionError("configuration read"))
        assert resolve_run_execution(requested=RunExecution.HOSTED) is RunExecution.HOSTED
        reader.assert_not_called()

    def test_the_kit_default_is_local(self) -> None:
        """The packaged default, which the booted test configuration carries, runs locally."""
        assert get_config().run.execution is RunExecution.LOCAL
        assert configured_run_execution() is RunExecution.LOCAL

    def test_without_a_boot_the_setting_is_read_from_the_configuration_files(self, mocker: MockerFixture) -> None:
        """A hosted run does not boot, so the setting is read from the same layers a boot would merge."""
        mocker.patch(f"{EXECUTION_MODULE}.get_optional_config", return_value=None)
        hosted_config = get_config().model_copy(update={"run": RunConfig(execution=RunExecution.HOSTED)})
        load = mocker.patch.object(config_manager, "load_config_validated", return_value=hosted_config)

        assert configured_run_execution() is RunExecution.HOSTED
        load.assert_called_once_with(config_cls=PipelexConfig)

    def test_a_configuration_file_sets_the_default(self, tmp_path: Path) -> None:
        """`[run] execution = "hosted"` in a configuration directory validates into the hosted default."""
        (tmp_path / "pipelex.toml").write_text('[run]\nexecution = "hosted"\n', encoding="utf-8")
        loaded = config_manager.load_config_validated(config_cls=PipelexConfig, config_dir=tmp_path)
        assert loaded.run.execution is RunExecution.HOSTED

    @pytest.mark.parametrize(
        ("hosted", "expected"),
        [
            (True, RunExecution.HOSTED),
            (False, RunExecution.LOCAL),
            (None, None),
        ],
    )
    def test_the_hosted_flag_pair_maps_onto_the_execution(self, hosted: bool | None, expected: RunExecution | None) -> None:
        """`--hosted` and `--local` are one flag pair; leaving both out requests nothing."""
        assert RunExecution.from_hosted_flag(hosted=hosted) is expected

    @pytest.mark.parametrize(("execution", "is_hosted"), [(RunExecution.HOSTED, True), (RunExecution.LOCAL, False)])
    def test_is_hosted(self, execution: RunExecution, is_hosted: bool) -> None:
        assert execution.is_hosted is is_hosted
