"""Unit tests for the `pipelex build runner` core logic (_prepare_runner_core).

The library plumbing and the codegen engine seams are mocked at the module namespace, so these
tests pin the runner-core wiring (pipe selection, output paths, the structures projection hand-off,
and the exit codes), not the engine itself (covered by the codegen unit tests).
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
        """Stub library plumbing, the codegen engine seams, and runner codegen."""
        library_manager = mocker.MagicMock()
        library_manager.get_crate.return_value = None  # default: no crate -> no structures projection
        mocker.patch(f"{MODULE}.get_library_manager", return_value=library_manager)
        mocker.patch(f"{MODULE}.get_current_library_id_or_none", return_value="lib_id")
        blueprint = SimpleNamespace(main_pipe="bundle_main", pipe=None)
        validate_result = SimpleNamespace(blueprints=[blueprint])
        return {
            "library_manager": library_manager,
            "validate_bundle": mocker.patch(f"{MODULE}.validate_bundle", new=mocker.AsyncMock(return_value=validate_result)),
            "get_required_entry_pipe": mocker.patch(f"{MODULE}.get_required_entry_pipe", return_value=SimpleNamespace(code="bundle_main")),
            "normalize_crate": mocker.patch(f"{MODULE}.normalize_crate"),
            "emit_types": mocker.patch(f"{MODULE}.emit_types", return_value=[]),
            "write_stamped_projection": mocker.patch(
                f"{MODULE}.write_stamped_projection",
                return_value=SimpleNamespace(written=["structures.py"], unchanged=[], removed=[]),
            ),
            "resolve_concepts": mocker.patch(f"{MODULE}.resolve_concepts_from_crate"),
            "runtime_to_emitted": mocker.patch(f"{MODULE}.runtime_to_emitted_class_names", return_value={"demo__Invoice": "Invoice"}),
            "generate_runner_code": mocker.patch(f"{MODULE}.generate_runner_code", return_value="# runner code\n"),
        }

    def test_bundle_main_pipe_writes_runner_next_to_bundle(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Without --pipe, the bundle's main_pipe names the default run_<pipe>.py file."""
        asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        core_mocks["get_required_entry_pipe"].assert_called_once_with(pipe_code="bundle_main")
        runner_file = tmp_path / "run_bundle_main.py"
        assert runner_file.read_text(encoding="utf-8") == "# runner code\n"
        codegen_kwargs = core_mocks["generate_runner_code"].call_args.kwargs
        assert codegen_kwargs["output_multiplicity"] is False
        assert codegen_kwargs["library_dir"] == str(tmp_path.resolve())

    def test_structures_projection_emitted_into_structures_dir(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """With a crate available, the types projection is written into structures/ next to the
        runner and the emitted-name mapping is handed to the runner-code generator.
        """
        core_mocks["library_manager"].get_crate.return_value = SimpleNamespace()

        asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        write_kwargs = core_mocks["write_stamped_projection"].call_args.kwargs
        assert write_kwargs["output_dir"] == tmp_path / "structures"
        codegen_kwargs = core_mocks["generate_runner_code"].call_args.kwargs
        assert codegen_kwargs["class_name_overrides"] == {"demo__Invoice": "Invoice"}

    def test_no_crate_skips_structures_projection(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Without a crate (nothing loaded), the runner is still generated with no overrides."""
        asyncio.run(_prepare_runner_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        core_mocks["write_stamped_projection"].assert_not_called()
        codegen_kwargs = core_mocks["generate_runner_code"].call_args.kwargs
        assert codegen_kwargs["class_name_overrides"] == {}

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
