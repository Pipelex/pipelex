"""Unit tests for the Temporal worker CLI entry point — project resolution, fast-fail queue check, library load, arg wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from typer.testing import CliRunner

from pipelex.system.configuration.exceptions import WorkerTaskQueueUnknownError
from pipelex.system.runtime import RunMode
from pipelex.temporal import worker_cli

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

DEFAULT_TASK_QUEUE = "default_queue"
PYPROJECT_WITH_PROJECT_NAME = {"project": {"name": "my-project"}}


class TestWorkerCli:
    @pytest.fixture
    def boot_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub everything configure() touches: pyproject load, Pipelex boot, config, hub library getters, and the worker loop."""
        config = mocker.MagicMock()
        config.temporal.worker_config.default_task_queue = DEFAULT_TASK_QUEUE
        config.temporal.is_enabled = True
        library_manager = mocker.MagicMock()
        return {
            "config": config,
            "load_toml": mocker.patch.object(worker_cli, "load_toml_from_path", return_value=PYPROJECT_WITH_PROJECT_NAME),
            "pipelex_make": mocker.patch.object(worker_cli.Pipelex, "make"),
            "get_config": mocker.patch.object(worker_cli, "get_config", return_value=config),
            "set_run_mode": mocker.patch.object(type(worker_cli.runtime_manager), "set_run_mode"),
            "library_manager": library_manager,
            "get_library_manager": mocker.patch("pipelex.hub.get_library_manager", return_value=library_manager),
            "set_current_library": mocker.patch("pipelex.hub.set_current_library"),
            "resolve_library_dirs": mocker.patch("pipelex.hub.resolve_library_dirs", return_value=([], "PIPELEXPATH")),
            "run_worker": mocker.patch.object(worker_cli, "run_worker", new=mocker.AsyncMock(return_value=None)),
        }

    @pytest.mark.parametrize("project", [None, "chosen-project"])
    @pytest.mark.asyncio
    async def test_run_worker_forwards_kwargs_to_task_manager(self, mocker: MockerFixture, project: str | None) -> None:
        """run_worker hands all worker options to the task manager, for both implicit and explicit project."""
        task_manager = mocker.MagicMock()
        task_manager.run_worker = mocker.AsyncMock(return_value=None)
        mocker.patch.object(worker_cli, "get_task_manager", return_value=task_manager)

        await worker_cli.run_worker(
            project=project,
            is_not_sandboxed=True,
            is_unit_testing=False,
            task_queue="some_queue",
            scope_name="router",
            profile_name="anthropic-tier4",
        )

        task_manager.run_worker.assert_awaited_once_with(
            is_not_sandboxed=True,
            is_unit_testing=False,
            task_queue="some_queue",
            scope_name="router",
            profile_name="anthropic-tier4",
        )

    def test_explicit_project_skips_pyproject(self, boot_mocks: dict[str, Any]) -> None:
        """An explicit project argument bypasses pyproject.toml entirely."""
        worker_cli.configure(project="explicit-project")

        boot_mocks["load_toml"].assert_not_called()
        boot_mocks["pipelex_make"].assert_called_once_with(temporal_enabled=True)
        assert boot_mocks["run_worker"].call_args.kwargs["project"] == "explicit-project"

    def test_project_resolved_from_pyproject_project_name(self, boot_mocks: dict[str, Any]) -> None:
        """With no argument, the project name comes from [project].name in pyproject.toml."""
        worker_cli.configure()

        boot_mocks["load_toml"].assert_called_once_with(path="pyproject.toml")
        assert boot_mocks["run_worker"].call_args.kwargs["project"] == "my-project"

    def test_project_falls_back_to_poetry_name(self, boot_mocks: dict[str, Any]) -> None:
        """When [project].name is absent, [tool.poetry].name is used."""
        boot_mocks["load_toml"].return_value = {"tool": {"poetry": {"name": "poetry-project"}}}

        worker_cli.configure()

        assert boot_mocks["run_worker"].call_args.kwargs["project"] == "poetry-project"

    def test_missing_project_name_raises(self, boot_mocks: dict[str, Any]) -> None:
        """A pyproject.toml without any project name aborts before booting Pipelex."""
        boot_mocks["load_toml"].return_value = {"tool": {"poetry": {}}}

        with pytest.raises(ValueError, match=r"Project name not found in pyproject\.toml"):
            worker_cli.configure()

        boot_mocks["pipelex_make"].assert_not_called()

    def test_unit_testing_flag_sets_run_mode(self, boot_mocks: dict[str, Any]) -> None:
        """--is-unit-testing switches the runtime manager to UNIT_TEST mode."""
        worker_cli.configure(is_unit_testing=True)

        boot_mocks["set_run_mode"].assert_called_once_with(RunMode.UNIT_TEST)

    def test_no_unit_testing_flag_leaves_run_mode_alone(self, boot_mocks: dict[str, Any]) -> None:
        """Without the flag, the run mode is never touched."""
        worker_cli.configure()

        boot_mocks["set_run_mode"].assert_not_called()

    @pytest.mark.parametrize(
        ("topic", "task_queue", "expected_validated_queue"),
        [
            ("explicit_queue", "custom_queue", "custom_queue"),
            ("default_queue_fallback", None, DEFAULT_TASK_QUEUE),
        ],
    )
    def test_task_queue_validated_before_library_load(
        self,
        boot_mocks: dict[str, Any],
        mocker: MockerFixture,
        topic: str,
        task_queue: str | None,
        expected_validated_queue: str,
    ) -> None:
        """The effective task queue (explicit or config default) is validated against known queues."""
        worker_cli.configure(task_queue=task_queue)

        validate_mock = boot_mocks["config"].temporal.validate_task_queue_known
        assert validate_mock.call_args_list == [mocker.call(expected_validated_queue)], f"Wrong validated queue for {topic}"

    def test_unknown_task_queue_fast_fails_before_library_load(self, boot_mocks: dict[str, Any]) -> None:
        """A typo'd task queue aborts before any library loading or worker start."""
        boot_mocks["config"].temporal.validate_task_queue_known.side_effect = WorkerTaskQueueUnknownError("unknown queue 'tyop'")

        with pytest.raises(WorkerTaskQueueUnknownError, match="unknown queue 'tyop'"):
            worker_cli.configure(task_queue="tyop")

        boot_mocks["get_library_manager"].assert_not_called()
        boot_mocks["run_worker"].assert_not_called()

    def test_library_loaded_from_resolved_dirs(self, boot_mocks: dict[str, Any]) -> None:
        """Resolved library dirs are loaded into the worker_base library."""
        boot_mocks["resolve_library_dirs"].return_value = (["libs_a", "libs_b"], "PIPELEXPATH")

        worker_cli.configure()

        boot_mocks["library_manager"].open_library.assert_called_once_with(library_id="worker_base")
        boot_mocks["set_current_library"].assert_called_once_with(library_id="worker_base")
        boot_mocks["resolve_library_dirs"].assert_called_once_with(library_dirs=None)
        boot_mocks["library_manager"].load_libraries.assert_called_once_with(library_id="worker_base", library_dirs=["libs_a", "libs_b"])

    def test_no_library_dirs_skips_load(self, boot_mocks: dict[str, Any]) -> None:
        """With no resolved dirs (PIPELEXPATH unset), the library load is skipped but the library is still opened."""
        worker_cli.configure()

        boot_mocks["library_manager"].open_library.assert_called_once_with(library_id="worker_base")
        boot_mocks["library_manager"].load_libraries.assert_not_called()

    def test_temporal_disabled_in_config_is_forced_on(self, boot_mocks: dict[str, Any], mocker: MockerFixture) -> None:
        """When temporal.is_enabled is false, worker mode forces it on via a config copy."""
        temporal_mock = boot_mocks["config"].temporal
        temporal_mock.is_enabled = False
        temporal_mock.model_copy.return_value = mocker.sentinel.updated_temporal

        worker_cli.configure()

        temporal_mock.model_copy.assert_called_once_with(update={"is_enabled": True})
        assert boot_mocks["config"].temporal is mocker.sentinel.updated_temporal

    def test_temporal_enabled_in_config_is_left_alone(self, boot_mocks: dict[str, Any]) -> None:
        """When temporal.is_enabled is already true, the config is not copied or reassigned."""
        temporal_mock = boot_mocks["config"].temporal

        worker_cli.configure()

        temporal_mock.model_copy.assert_not_called()
        assert boot_mocks["config"].temporal is temporal_mock

    def test_cli_arg_wiring_reaches_run_worker(self, boot_mocks: dict[str, Any]) -> None:
        """All CLI options travel through Typer parsing into run_worker, with the correct keyword wiring."""
        runner = CliRunner()

        result = runner.invoke(
            worker_cli.app,
            [
                "cli-project",
                "--is-not-sandboxed",
                "--is-unit-testing",
                "--task-queue",
                "queue_from_cli",
                "--scope",
                "router",
                "--profile",
                "anthropic-tier4",
            ],
        )

        assert result.exit_code == 0, result.output
        boot_mocks["run_worker"].assert_called_once_with(
            project="cli-project",
            is_not_sandboxed=True,
            is_unit_testing=True,
            task_queue="queue_from_cli",
            scope_name="router",
            profile_name="anthropic-tier4",
        )

    def test_cli_defaults_reach_run_worker(self, boot_mocks: dict[str, Any]) -> None:
        """Invoking with no arguments resolves the project from pyproject and passes default options."""
        runner = CliRunner()

        result = runner.invoke(worker_cli.app, [])

        assert result.exit_code == 0, result.output
        boot_mocks["run_worker"].assert_called_once_with(
            project="my-project",
            is_not_sandboxed=False,
            is_unit_testing=False,
            task_queue=None,
            scope_name=None,
            profile_name=None,
        )
