"""Unit tests for the `pipelex build runner` core logic (_prepare_runner_core).

The registry getters are mocked at the module namespace so the real class/func
registries of the module-scoped Pipelex are never torn down by these tests.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.commands.build.runner._runner_core import _prepare_runner_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

MODULE = "pipelex.cli.commands.build.runner._runner_core"


class TestPrepareRunnerCore:
    @pytest.fixture
    def core_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub library plumbing, registries, structure generation and runner codegen."""
        library_manager = mocker.MagicMock()
        library_manager.open_library.return_value = ("lib_id", mocker.MagicMock())
        mocker.patch(f"{MODULE}.get_library_manager", return_value=library_manager)
        mocker.patch(f"{MODULE}.set_current_library")
        mocker.patch(f"{MODULE}.resolve_library_dirs", return_value=([], "defaults"))
        mocker.patch(f"{MODULE}.get_class_registry", return_value=mocker.MagicMock())
        mocker.patch(f"{MODULE}.get_func_registry", return_value=mocker.MagicMock())
        mocker.patch(f"{MODULE}.ClassRegistryUtils")
        blueprint = SimpleNamespace(main_pipe="bundle_main", pipe=None)
        validate_result = SimpleNamespace(blueprints=[blueprint])
        return {
            "validate_bundle": mocker.patch(f"{MODULE}.validate_bundle", new=mocker.AsyncMock(return_value=validate_result)),
            "get_required_pipe": mocker.patch(f"{MODULE}.get_required_pipe", return_value=SimpleNamespace(code="bundle_main")),
            "generate_structures": mocker.patch(f"{MODULE}.generate_structures_from_blueprints", return_value=[]),
            "generate_runner_code": mocker.patch(f"{MODULE}.generate_runner_code", return_value="# runner code\n"),
        }

    def test_bundle_main_pipe_writes_runner_next_to_bundle(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Without --pipe, the bundle's main_pipe names the default run_<pipe>.py file."""
        asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        core_mocks["get_required_pipe"].assert_called_once_with(pipe_code="bundle_main")
        runner_file = tmp_path / "run_bundle_main.py"
        assert runner_file.read_text(encoding="utf-8") == "# runner code\n"
        codegen_kwargs = core_mocks["generate_runner_code"].call_args.kwargs
        assert codegen_kwargs["output_multiplicity"] is False
        assert codegen_kwargs["library_dir"] == str(tmp_path.resolve())

    def test_structures_generated_into_output_dir(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Structure files are generated into a structures/ dir next to the runner."""
        core_mocks["generate_structures"].return_value = [("demo", "Invoice")]

        asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        structures_kwargs = core_mocks["generate_structures"].call_args.kwargs
        assert structures_kwargs["output_directory"] == tmp_path / "structures"
        assert structures_kwargs["target_path"] == tmp_path

    @pytest.mark.usefixtures("core_mocks")
    def test_explicit_output_path_wins(self, tmp_path: Path) -> None:
        """An explicit output path is used verbatim for the runner file."""
        target_path = tmp_path / "generated" / "my_runner.py"

        asyncio.run(_prepare_runner_core(pipe_code="my_pipe", bundle_path=tmp_path / "demo.mthds", output_path=target_path))

        assert target_path.read_text(encoding="utf-8") == "# runner code\n"

    def test_output_multiplicity_detected_from_pipe_blueprint(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A pipe whose output declares a multiplicity generates a list-aware runner."""
        blueprint = SimpleNamespace(
            main_pipe="bundle_main",
            pipe={"bundle_main": SimpleNamespace(output="Invoice[]")},
        )
        core_mocks["validate_bundle"].return_value = SimpleNamespace(blueprints=[blueprint])

        asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        codegen_kwargs = core_mocks["generate_runner_code"].call_args.kwargs
        assert codegen_kwargs["output_multiplicity"] is True

    @pytest.mark.usefixtures("core_mocks")
    def test_no_bundle_exits(self) -> None:
        """The runner build requires a bundle file."""
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_prepare_runner_core(pipe_code="my_pipe", bundle_path=None))

        assert exc_info.value.exit_code == 1

    def test_bundle_without_main_pipe_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle without main_pipe and no --pipe is an error."""
        core_mocks["validate_bundle"].return_value = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe=None, pipe=None)])

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1

    def test_validate_bundle_error_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle validation failure exits 1."""
        core_mocks["validate_bundle"].side_effect = ValidateBundleError("broken bundle")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1

    def test_runner_codegen_failure_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A failure while generating runner code exits 1."""
        core_mocks["generate_runner_code"].side_effect = RuntimeError("codegen exploded")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1
