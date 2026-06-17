"""Unit tests for the `pipelex build inputs` core logic (_generate_inputs_core)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.commands.build.inputs._inputs_core import _generate_inputs_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

MODULE = "pipelex.cli.commands.build.inputs._inputs_core"


class TestGenerateInputsCore:
    @pytest.fixture
    def core_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub the library plumbing, bundle validation, pipe lookup and input rendering."""
        library_manager = mocker.MagicMock()
        library_manager.open_library.return_value = ("lib_id", mocker.MagicMock())
        mocker.patch(f"{MODULE}.get_library_manager", return_value=library_manager)
        mocker.patch(f"{MODULE}.set_current_library")
        mocker.patch(f"{MODULE}.resolve_library_dirs", return_value=([], "defaults"))
        validate_result = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe="bundle_main")])
        return {
            "validate_bundle": mocker.patch(f"{MODULE}.validate_bundle", new=mocker.AsyncMock(return_value=validate_result)),
            "get_required_pipe": mocker.patch(f"{MODULE}.get_required_pipe", return_value=SimpleNamespace(code="bundle_main")),
            "render_inputs": mocker.patch(f"{MODULE}.render_inputs", return_value='{\n  "topic": "your topic"\n}'),
        }

    def test_bundle_main_pipe_writes_inputs_next_to_bundle(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Without --pipe, the bundle's main_pipe is used and inputs.json lands next to the bundle."""
        bundle_path = tmp_path / "demo.mthds"

        asyncio.run(_generate_inputs_core(pipe_code=None, bundle_path=bundle_path))

        core_mocks["get_required_pipe"].assert_called_once_with(pipe_code="bundle_main")
        inputs_file = tmp_path / "inputs.json"
        assert inputs_file.read_text(encoding="utf-8") == '{\n  "topic": "your topic"\n}'

    def test_explicit_pipe_code_wins_over_main_pipe(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """With --pipe, the explicit pipe code is used even when the bundle has a main_pipe."""
        bundle_path = tmp_path / "demo.mthds"

        asyncio.run(_generate_inputs_core(pipe_code="my_pipe", bundle_path=bundle_path))

        core_mocks["get_required_pipe"].assert_called_once_with(pipe_code="my_pipe")

    def test_bundle_without_main_pipe_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle without main_pipe and no --pipe is an error."""
        core_mocks["validate_bundle"].return_value = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe=None)])

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_inputs_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("core_mocks")
    def test_no_bundle_and_no_pipe_exits(self) -> None:
        """Neither a bundle nor a pipe code is an immediate error."""
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_inputs_core(pipe_code=None, bundle_path=None))

        assert exc_info.value.exit_code == 1

    def test_validate_bundle_error_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle validation failure exits 1."""
        core_mocks["validate_bundle"].side_effect = ValidateBundleError("broken bundle")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_inputs_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1

    def test_no_inputs_required_exits_zero(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A pipe needing no inputs exits 0 with a friendly message, not an error."""
        core_mocks["render_inputs"].side_effect = NoInputsRequiredError("pipe has no inputs")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_inputs_core(pipe_code="my_pipe", bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 0

    @pytest.mark.usefixtures("core_mocks")
    def test_explicit_output_path_wins(self, tmp_path: Path) -> None:
        """An explicit output path is used verbatim, parents created."""
        target_path = tmp_path / "deep" / "custom_inputs.json"

        asyncio.run(_generate_inputs_core(pipe_code="my_pipe", bundle_path=tmp_path / "demo.mthds", output_path=target_path))

        assert target_path.read_text(encoding="utf-8") == '{\n  "topic": "your topic"\n}'

    @pytest.mark.usefixtures("core_mocks")
    def test_no_bundle_defaults_to_results_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With only a pipe code, the file goes to results/inputs.json under the cwd."""
        monkeypatch.chdir(tmp_path)

        asyncio.run(_generate_inputs_core(pipe_code="my_pipe", bundle_path=None))

        assert (tmp_path / "results" / "inputs.json").exists()
