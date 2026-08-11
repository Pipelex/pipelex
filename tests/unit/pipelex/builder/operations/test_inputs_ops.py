"""Unit tests for build_inputs_for_pipe in builder operations (inputs_ops)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.builder.operations.inputs_ops import build_inputs_for_pipe

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

MODULE = "pipelex.builder.operations.inputs_ops"


class TestBuildInputsForPipe:
    @pytest.fixture
    def ops_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub the library plumbing, bundle validation, pipe lookup and input rendering."""
        library_manager = mocker.MagicMock()
        library_manager.open_library.return_value = ("lib_id", mocker.MagicMock())
        validate_result = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe="bundle_main", domain="demo_domain")])
        return {
            "library_manager": library_manager,
            "get_library_manager": mocker.patch(f"{MODULE}.get_library_manager", return_value=library_manager),
            "set_current_library": mocker.patch(f"{MODULE}.set_current_library"),
            "resolve_library_dirs": mocker.patch(f"{MODULE}.resolve_library_dirs", return_value=([], "defaults")),
            "validate_bundle": mocker.patch(f"{MODULE}.validate_bundle", new=mocker.AsyncMock(return_value=validate_result)),
            "get_required_entry_pipe": mocker.patch(
                f"{MODULE}.get_required_entry_pipe", return_value=SimpleNamespace(code="bundle_main", inputs=SimpleNamespace(root={}))
            ),
            "render_inputs": mocker.patch(f"{MODULE}.render_inputs", return_value='{\n  "topic": "your topic"\n}'),
        }

    def test_mthds_contents_first_main_pipe_wins_domain_qualified(self, ops_mocks: dict[str, Any]) -> None:
        """Without a pipe code, the first blueprint declaring a main_pipe wins, domain-qualified."""
        ops_mocks["validate_bundle"].return_value = SimpleNamespace(
            blueprints=[
                SimpleNamespace(main_pipe=None, domain="other_domain"),
                SimpleNamespace(main_pipe="main", domain="domain"),
                SimpleNamespace(main_pipe="later_main", domain="later_domain"),
            ]
        )

        result = asyncio.run(build_inputs_for_pipe(mthds_contents=["mthds content"]))

        ops_mocks["get_required_entry_pipe"].assert_called_once_with(pipe_code="domain.main")
        assert result["pipe_code"] == "domain.main"

    def test_mthds_contents_validates_with_allow_signatures(self, ops_mocks: dict[str, Any]) -> None:
        """The mthds_contents branch validates with allow_signatures=True — placeholders are tolerated on purpose."""
        library_dirs = [Path("/some/lib")]

        asyncio.run(build_inputs_for_pipe(mthds_contents=["mthds content"], library_dirs=library_dirs))

        ops_mocks["validate_bundle"].assert_awaited_once_with(
            mthds_contents=["mthds content"],
            library_dirs=library_dirs,
            allow_signatures=True,
        )

    def test_mthds_contents_without_any_main_pipe_raises(self, ops_mocks: dict[str, Any]) -> None:
        """When no blueprint declares a main_pipe and no pipe code is given, a ValueError is raised."""
        ops_mocks["validate_bundle"].return_value = SimpleNamespace(
            blueprints=[
                SimpleNamespace(main_pipe=None, domain="alpha_domain"),
                SimpleNamespace(main_pipe=None, domain="beta_domain"),
            ]
        )

        with pytest.raises(ValueError, match="Bundle does not declare a main_pipe"):
            asyncio.run(build_inputs_for_pipe(mthds_contents=["mthds content"]))

    def test_mthds_contents_explicit_pipe_code_skips_scan(self, ops_mocks: dict[str, Any]) -> None:
        """An explicit pipe code is used verbatim, ignoring the blueprints' main_pipe declarations."""
        result = asyncio.run(build_inputs_for_pipe(pipe_code="explicit_pipe", mthds_contents=["mthds content"]))

        ops_mocks["get_required_entry_pipe"].assert_called_once_with(pipe_code="explicit_pipe")
        assert result["pipe_code"] == "explicit_pipe"

    def test_bundle_path_validates_file_and_qualifies_main_pipe(self, ops_mocks: dict[str, Any], tmp_path: Path) -> None:
        """The bundle_path branch validates by file path and domain-qualifies the bundle's main_pipe."""
        bundle_path = tmp_path / "demo.mthds"

        result = asyncio.run(build_inputs_for_pipe(bundle_path=bundle_path))

        ops_mocks["validate_bundle"].assert_awaited_once_with(
            mthds_file_path=bundle_path,
            library_dirs=None,
            allow_signatures=True,
        )
        ops_mocks["get_required_entry_pipe"].assert_called_once_with(pipe_code="demo_domain.bundle_main")
        assert result["pipe_code"] == "demo_domain.bundle_main"

    def test_bundle_path_without_main_pipe_raises_with_path(self, ops_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A bundle file without a main_pipe raises a ValueError naming the bundle path."""
        bundle_path = tmp_path / "demo.mthds"
        ops_mocks["validate_bundle"].return_value = SimpleNamespace(blueprints=[SimpleNamespace(main_pipe=None, domain="demo_domain")])

        with pytest.raises(ValueError, match="does not declare a main_pipe") as exc_info:
            asyncio.run(build_inputs_for_pipe(bundle_path=bundle_path))

        assert str(bundle_path) in str(exc_info.value)

    def test_bundle_path_explicit_pipe_code_wins(self, ops_mocks: dict[str, Any], tmp_path: Path) -> None:
        """With a bundle path, an explicit pipe code overrides the bundle's main_pipe."""
        result = asyncio.run(build_inputs_for_pipe(pipe_code="explicit_pipe", bundle_path=tmp_path / "demo.mthds"))

        ops_mocks["get_required_entry_pipe"].assert_called_once_with(pipe_code="explicit_pipe")
        assert result["pipe_code"] == "explicit_pipe"

    def test_no_bundle_loads_libraries_from_resolved_dirs(self, ops_mocks: dict[str, Any]) -> None:
        """Without a bundle, the library is opened, set current, and non-empty resolved dirs are loaded."""
        resolved_dirs = [Path("/resolved/dir")]
        ops_mocks["resolve_library_dirs"].return_value = (resolved_dirs, "explicit")

        asyncio.run(build_inputs_for_pipe(pipe_code="my_pipe", library_dirs=resolved_dirs))

        ops_mocks["library_manager"].open_library.assert_called_once_with()
        ops_mocks["set_current_library"].assert_called_once_with(library_id="lib_id")
        ops_mocks["resolve_library_dirs"].assert_called_once_with(resolved_dirs)
        ops_mocks["library_manager"].load_libraries.assert_called_once_with(library_id="lib_id", library_dirs=resolved_dirs)
        ops_mocks["validate_bundle"].assert_not_awaited()

    def test_no_bundle_empty_resolved_dirs_skips_loading(self, ops_mocks: dict[str, Any]) -> None:
        """Without a bundle, empty resolved dirs mean no library loading at all."""
        asyncio.run(build_inputs_for_pipe(pipe_code="my_pipe"))

        ops_mocks["library_manager"].load_libraries.assert_not_called()
        ops_mocks["set_current_library"].assert_called_once_with(library_id="lib_id")

    def test_no_bundle_and_no_pipe_code_raises(self, ops_mocks: dict[str, Any]) -> None:
        """Neither a bundle nor a pipe code is an immediate error."""
        with pytest.raises(ValueError, match="No pipe code specified"):
            asyncio.run(build_inputs_for_pipe())

        ops_mocks["get_required_entry_pipe"].assert_not_called()

    def test_happy_path_return_shape(self, ops_mocks: dict[str, Any]) -> None:
        """The result carries success, the resolved pipe code, and the parsed inputs dict from render_inputs."""
        result = asyncio.run(build_inputs_for_pipe(pipe_code="my_pipe"))

        the_pipe = ops_mocks["get_required_entry_pipe"].return_value
        ops_mocks["render_inputs"].assert_called_once_with(the_pipe, indent=2, explicit=False)
        assert result == {
            "success": True,
            "pipe_code": "my_pipe",
            "inputs": {"topic": "your topic"},
            "concept_comments": {},
        }
