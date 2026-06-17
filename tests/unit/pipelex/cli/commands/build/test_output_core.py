"""Unit tests for the `pipelex build output` core logic (_generate_output_core)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.commands.build.output._output_core import _generate_output_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

MODULE = "pipelex.cli.commands.build.output._output_core"


class TestGenerateOutputCore:
    @pytest.fixture
    def core_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub the library plumbing, bundle validation, pipe lookup and output rendering."""
        library_manager = mocker.MagicMock()
        library_manager.open_library.return_value = ("lib_id", mocker.MagicMock())
        mocker.patch(f"{MODULE}.get_library_manager", return_value=library_manager)
        mocker.patch(f"{MODULE}.set_current_library")
        mocker.patch(f"{MODULE}.resolve_library_dirs", return_value=([], "defaults"))
        validate_result = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe="bundle_main")])
        return {
            "validate_bundle": mocker.patch(f"{MODULE}.validate_bundle", new=mocker.AsyncMock(return_value=validate_result)),
            "get_required_pipe": mocker.patch(f"{MODULE}.get_required_pipe", return_value=SimpleNamespace(code="bundle_main")),
            "render_output": mocker.patch(f"{MODULE}.render_output", return_value='{"answer": 42}'),
        }

    def test_bundle_main_pipe_writes_json_next_to_bundle(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Without --pipe, the bundle's main_pipe is used and output.json lands next to the bundle."""
        asyncio.run(_generate_output_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        core_mocks["get_required_pipe"].assert_called_once_with(pipe_code="bundle_main")
        assert (tmp_path / "output.json").read_text(encoding="utf-8") == '{"answer": 42}'

    @pytest.mark.usefixtures("core_mocks")
    def test_python_format_defaults_to_output_py(self, tmp_path: Path) -> None:
        """The PYTHON format defaults to output.py next to the bundle."""
        asyncio.run(
            _generate_output_core(
                pipe_code="my_pipe",
                bundle_path=tmp_path / "demo.mthds",
                output_format=ConceptRepresentationFormat.PYTHON,
            )
        )

        assert (tmp_path / "output.py").exists()

    @pytest.mark.usefixtures("core_mocks")
    def test_schema_format_defaults_to_results_dir_without_bundle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without a bundle, the SCHEMA format goes to results/output_schema.json."""
        monkeypatch.chdir(tmp_path)

        asyncio.run(_generate_output_core(pipe_code="my_pipe", output_format=ConceptRepresentationFormat.SCHEMA))

        assert (tmp_path / "results" / "output_schema.json").exists()

    @pytest.mark.usefixtures("core_mocks")
    def test_explicit_output_path_wins(self, tmp_path: Path) -> None:
        """An explicit output path is used verbatim."""
        target_path = tmp_path / "deep" / "custom_output.json"

        asyncio.run(_generate_output_core(pipe_code="my_pipe", bundle_path=tmp_path / "demo.mthds", output_path=target_path))

        assert target_path.read_text(encoding="utf-8") == '{"answer": 42}'

    def test_bundle_without_main_pipe_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle without main_pipe and no --pipe is an error."""
        core_mocks["validate_bundle"].return_value = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe=None)])

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_output_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("core_mocks")
    def test_no_bundle_and_no_pipe_exits(self) -> None:
        """Neither a bundle nor a pipe code is an immediate error."""
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_output_core(pipe_code=None, bundle_path=None))

        assert exc_info.value.exit_code == 1

    def test_validate_bundle_error_exits(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle validation failure exits 1."""
        core_mocks["validate_bundle"].side_effect = ValidateBundleError("broken bundle")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_output_core(pipe_code=None, bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1

    def test_render_value_error_exits_zero(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A ValueError from rendering (e.g. nothing to represent) exits 0, not 1."""
        core_mocks["render_output"].side_effect = ValueError("nothing to render")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_output_core(pipe_code="my_pipe", bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 0

    def test_render_unexpected_error_exits_one(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """An unexpected rendering failure exits 1."""
        core_mocks["render_output"].side_effect = RuntimeError("render exploded")

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_generate_output_core(pipe_code="my_pipe", bundle_path=tmp_path / "demo.mthds"))

        assert exc_info.value.exit_code == 1
