"""Unit tests for the `pipelex build inputs --format toml` path of _generate_inputs_core."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.commands.build.inputs._inputs_core import (
    _generate_inputs_core,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

MODULE = "pipelex.cli.commands.build.inputs._inputs_core"

TOML_TEMPLATE = '[topic]\nconcept = "demo.Topic"\n'


class TestGenerateInputsCoreToml:
    @pytest.fixture
    def core_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub the library plumbing, bundle validation, pipe lookup and both renderers."""
        library_manager = mocker.MagicMock()
        library_manager.open_library.return_value = ("lib_id", mocker.MagicMock())
        mocker.patch(f"{MODULE}.get_library_manager", return_value=library_manager)
        mocker.patch(f"{MODULE}.set_current_library")
        mocker.patch(f"{MODULE}.resolve_library_dirs", return_value=([], "defaults"))
        validate_result = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe="bundle_main")])
        return {
            "validate_bundle": mocker.patch(f"{MODULE}.validate_bundle", new=mocker.AsyncMock(return_value=validate_result)),
            "get_required_entry_pipe": mocker.patch(f"{MODULE}.get_required_entry_pipe", return_value=SimpleNamespace(code="bundle_main")),
            "render_inputs": mocker.patch(f"{MODULE}.render_inputs", return_value='{\n  "topic": "your topic"\n}'),
            "render_inputs_toml": mocker.patch(f"{MODULE}.render_inputs_toml", return_value=TOML_TEMPLATE),
        }

    def test_toml_format_writes_inputs_toml_next_to_bundle(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """With --format toml and no --output, the default filename becomes inputs.toml next to the bundle."""
        bundle_path = tmp_path / "demo.mthds"

        asyncio.run(_generate_inputs_core(pipe_code=None, bundle_path=bundle_path, template_format=InputsTemplateFormat.TOML))

        inputs_file = tmp_path / "inputs.toml"
        assert inputs_file.read_text(encoding="utf-8") == TOML_TEMPLATE
        core_mocks["render_inputs_toml"].assert_called_once()
        core_mocks["render_inputs"].assert_not_called()
        assert not (tmp_path / "inputs.json").exists()

    def test_toml_format_defaults_to_results_dir_without_bundle(
        self, core_mocks: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a bundle, --format toml lands in results/inputs.toml."""
        monkeypatch.chdir(tmp_path)

        asyncio.run(_generate_inputs_core(pipe_code="my_pipe", bundle_path=None, template_format=InputsTemplateFormat.TOML))

        inputs_file = tmp_path / "results" / "inputs.toml"
        assert inputs_file.read_text(encoding="utf-8") == TOML_TEMPLATE
        core_mocks["render_inputs"].assert_not_called()

    def test_explicit_output_path_wins_over_toml_default_name(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """An explicit --output is used verbatim in TOML mode too."""
        target_path = tmp_path / "custom" / "my_inputs.toml"

        asyncio.run(
            _generate_inputs_core(
                pipe_code="my_pipe",
                bundle_path=tmp_path / "demo.mthds",
                output_path=target_path,
                template_format=InputsTemplateFormat.TOML,
            )
        )

        assert target_path.read_text(encoding="utf-8") == TOML_TEMPLATE
        core_mocks["render_inputs_toml"].assert_called_once()

    def test_json_default_still_writes_inputs_json(self, core_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Leaving template_format at its default keeps the historical inputs.json behavior."""
        bundle_path = tmp_path / "demo.mthds"

        asyncio.run(_generate_inputs_core(pipe_code=None, bundle_path=bundle_path))

        inputs_file = tmp_path / "inputs.json"
        assert inputs_file.read_text(encoding="utf-8") == '{\n  "topic": "your topic"\n}'
        core_mocks["render_inputs_toml"].assert_not_called()
