"""Coverage for :meth:`PipelexMTHDSProtocol.validate` — report shaping and library restore.

Pins how the protocol wrapper maps a ``validate_bundle`` result onto
``PipelexValidationReport`` (single blueprint = dict, multiple = list; pipe structures
keyed by pipe code), the ``library_dirs``/``allow_signatures`` passthrough, and the
finally-block matrix that restores the caller's current-library and tears the
validation library down.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest

from pipelex.pipeline.runner import PipelexMTHDSProtocol, PipelexValidationReport

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType

_BLUEPRINT_DUMP_ONE = {"domain": "demo", "description": "first bundle"}
_BLUEPRINT_DUMP_TWO = {"domain": "extra", "description": "second bundle"}
_PIPE_DUMP_ONE = {"code": "first_pipe", "type": "PipeLLM"}
_PIPE_DUMP_TWO = {"code": "second_pipe", "type": "PipeFunc"}


class _ValidateEnv(NamedTuple):
    validate_bundle_mock: MockType
    current_library_mock: MockType
    set_current_library_mock: MockType
    clear_current_library_mock: MockType
    library_manager: MockType


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerValidateMethod:
    def _make_blueprint(self, mocker: MockerFixture, dump: dict[str, str]) -> MockType:
        blueprint: MockType = mocker.MagicMock(name=f"blueprint_{dump['domain']}")
        blueprint.model_dump.return_value = dump
        return blueprint

    def _make_pipe(self, mocker: MockerFixture, dump: dict[str, str]) -> MockType:
        pipe: MockType = mocker.MagicMock(name=f"pipe_{dump['code']}")
        pipe.code = dump["code"]
        pipe.model_dump.return_value = dump
        return pipe

    def _patch_env(
        self,
        mocker: MockerFixture,
        *,
        blueprint_dumps: list[dict[str, str]],
        pipe_dumps: list[dict[str, str]],
        library_ids: list[str | None],
    ) -> _ValidateEnv:
        """Patch ``validate_bundle`` and the library hub getters at the runner namespace.

        ``library_ids`` feeds ``get_current_library_id_or_none`` as a side_effect pair:
        first call = the caller's prev library, second call = the validation library left
        current by ``validate_bundle``.
        """
        result = mocker.MagicMock(name="validate_bundle_result")
        result.blueprints = [self._make_blueprint(mocker, dump) for dump in blueprint_dumps]
        result.pipes = [self._make_pipe(mocker, dump) for dump in pipe_dumps]
        validate_bundle_mock = mocker.patch(
            "pipelex.pipeline.runner.validate_bundle",
            new=mocker.AsyncMock(return_value=result),
        )
        current_library_mock = mocker.patch(
            "pipelex.pipeline.runner.get_current_library_id_or_none",
            side_effect=library_ids,
        )
        set_current_library_mock = mocker.patch("pipelex.pipeline.runner.set_current_library")
        clear_current_library_mock = mocker.patch("pipelex.pipeline.runner.clear_current_library")
        library_manager = mocker.patch("pipelex.pipeline.runner.get_library_manager").return_value
        return _ValidateEnv(
            validate_bundle_mock=validate_bundle_mock,
            current_library_mock=current_library_mock,
            set_current_library_mock=set_current_library_mock,
            clear_current_library_mock=clear_current_library_mock,
            library_manager=library_manager,
        )

    async def test_single_blueprint_reported_as_dict(self, mocker: MockerFixture) -> None:
        """One blueprint = a bare dict (not a one-item list), with pipe structures keyed by code."""
        env = self._patch_env(
            mocker,
            blueprint_dumps=[_BLUEPRINT_DUMP_ONE],
            pipe_dumps=[_PIPE_DUMP_ONE, _PIPE_DUMP_TWO],
            library_ids=[None, "val-lib"],
        )
        runner = PipelexMTHDSProtocol()

        report = await runner.validate(mthds_contents=["bundle-content"])

        assert isinstance(report, PipelexValidationReport)
        assert report.blueprint == _BLUEPRINT_DUMP_ONE
        assert report.graph_spec is None
        assert report.pipe_structures == {"first_pipe": _PIPE_DUMP_ONE, "second_pipe": _PIPE_DUMP_TWO}
        for blueprint in env.validate_bundle_mock.return_value.blueprints:
            blueprint.model_dump.assert_called_once_with(mode="json")
        for pipe in env.validate_bundle_mock.return_value.pipes:
            pipe.model_dump.assert_called_once_with(mode="json")

    async def test_multiple_blueprints_reported_as_list(self, mocker: MockerFixture) -> None:
        """Several blueprints = a list of dicts in declaration order."""
        self._patch_env(
            mocker,
            blueprint_dumps=[_BLUEPRINT_DUMP_ONE, _BLUEPRINT_DUMP_TWO],
            pipe_dumps=[_PIPE_DUMP_ONE],
            library_ids=[None, "val-lib"],
        )
        runner = PipelexMTHDSProtocol()

        report = await runner.validate(mthds_contents=["content-one", "content-two"])

        assert isinstance(report, PipelexValidationReport)
        assert report.blueprint == [_BLUEPRINT_DUMP_ONE, _BLUEPRINT_DUMP_TWO]
        assert report.pipe_structures == {"first_pipe": _PIPE_DUMP_ONE}

    async def test_library_dirs_converted_to_paths_and_allow_signatures_passthrough(self, mocker: MockerFixture) -> None:
        """Constructor library_dirs strings reach validate_bundle as Path objects;
        allow_signatures is forwarded verbatim.
        """
        env = self._patch_env(
            mocker,
            blueprint_dumps=[_BLUEPRINT_DUMP_ONE],
            pipe_dumps=[],
            library_ids=[None, "val-lib"],
        )
        runner = PipelexMTHDSProtocol(library_dirs=["dir_alpha", "nested/dir_beta"])

        await runner.validate(mthds_contents=["bundle-content"], allow_signatures=True)

        env.validate_bundle_mock.assert_awaited_once_with(
            mthds_contents=["bundle-content"],
            library_dirs=[Path("dir_alpha"), Path("nested/dir_beta")],
            allow_signatures=True,
        )

    async def test_no_library_dirs_passes_none(self, mocker: MockerFixture) -> None:
        """Without constructor library_dirs, validate_bundle receives None (strict default)."""
        env = self._patch_env(
            mocker,
            blueprint_dumps=[_BLUEPRINT_DUMP_ONE],
            pipe_dumps=[],
            library_ids=[None, "val-lib"],
        )
        runner = PipelexMTHDSProtocol()

        await runner.validate(mthds_contents=["bundle-content"])

        env.validate_bundle_mock.assert_awaited_once_with(
            mthds_contents=["bundle-content"],
            library_dirs=None,
            allow_signatures=False,
        )

    @pytest.mark.parametrize(
        ("prev_library_id", "validation_library_id", "expect_set_prev", "expect_clear", "expect_teardown"),
        [
            pytest.param("outer-lib", "val-lib", True, False, True, id="prev_set_restores_then_teardown"),
            pytest.param(None, "val-lib", False, True, True, id="prev_none_clears_then_teardown"),
            pytest.param("same-lib", "same-lib", False, False, False, id="validation_is_prev_no_restore_no_teardown"),
        ],
    )
    async def test_finally_restores_caller_library_matrix(
        self,
        mocker: MockerFixture,
        prev_library_id: str | None,
        validation_library_id: str,
        expect_set_prev: bool,
        expect_clear: bool,
        expect_teardown: bool,
    ) -> None:
        """The finally restores the caller's current-library and tears the validation
        library down — unless the validation library IS the caller's library.
        """
        env = self._patch_env(
            mocker,
            blueprint_dumps=[_BLUEPRINT_DUMP_ONE],
            pipe_dumps=[],
            library_ids=[prev_library_id, validation_library_id],
        )
        runner = PipelexMTHDSProtocol()

        await runner.validate(mthds_contents=["bundle-content"])

        if expect_set_prev:
            env.set_current_library_mock.assert_called_once_with(library_id=prev_library_id)
        else:
            env.set_current_library_mock.assert_not_called()
        if expect_clear:
            env.clear_current_library_mock.assert_called_once_with()
        else:
            env.clear_current_library_mock.assert_not_called()
        if expect_teardown:
            env.library_manager.teardown.assert_called_once_with(library_id=validation_library_id)
        else:
            env.library_manager.teardown.assert_not_called()
