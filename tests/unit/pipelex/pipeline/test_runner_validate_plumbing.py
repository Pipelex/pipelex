"""Unit coverage for the plumbing of :meth:`PipelexMTHDSProtocol.validate`.

Pins the wrapper's argument passthrough and library-lifecycle ``finally`` matrix with the
domain collaborators mocked out — complementing the real-library integration coverage in
``tests/integration/pipelex/pipeline/test_protocol_validate.py``. Specifically:

- constructor ``library_dirs`` strings are converted to ``Path`` objects (and ``None`` when
  unset) before reaching ``validate_bundle``, and ``allow_signatures`` is forwarded verbatim;
- the ``finally`` restores the caller's current-library (``set`` when it had one, ``clear`` when
  it didn't) and tears the validation library down — except when the validation library IS the
  caller's, where it must do neither. That last branch is unreachable with a real
  fresh-library ``validate_bundle`` (which always opens a new library id), so only a mocked
  unit test can pin the guard.

The report shaping itself is covered by ``test_validation_report.py`` and the integration
``test_protocol_validate.py``; this module deliberately mocks ``build_validation_report`` and
the artifact builders and asserts nothing about the returned report.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest

from pipelex.pipeline.runner import PipelexMTHDSProtocol

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType


class _ValidateEnv(NamedTuple):
    validate_bundle_mock: MockType
    set_current_library_mock: MockType
    clear_current_library_mock: MockType
    library_manager: MockType


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerValidatePlumbing:
    def _patch_env(self, mocker: MockerFixture, *, library_ids: list[str | None]) -> _ValidateEnv:
        """Patch ``validate_bundle``, the library hub getters, and the report-artifact builders
        at the ``validate_in_process`` namespace (the shared orchestrator the protocol ``validate``
        wrapper delegates to) so the body runs without a real loaded library.

        ``library_ids`` feeds ``get_current_library_id_or_none`` as a side_effect pair: first
        call = the caller's prev library, second call = the validation library left current by
        ``validate_bundle``.
        """
        validate_bundle_mock = mocker.patch(
            "pipelex.pipeline.validate_in_process.validate_bundle",
            new=mocker.AsyncMock(return_value=mocker.MagicMock(name="validate_bundle_result")),
        )
        mocker.patch("pipelex.pipeline.validate_in_process.get_current_library_id_or_none", side_effect=library_ids)
        set_current_library_mock = mocker.patch("pipelex.pipeline.validate_in_process.set_current_library")
        clear_current_library_mock = mocker.patch("pipelex.pipeline.validate_in_process.clear_current_library")
        library_manager = mocker.patch("pipelex.pipeline.validate_in_process.get_library_manager").return_value
        # These artifact builders run inside the library window; mock them so the body completes
        # without a real loaded library. Their output shaping is pinned in test_validation_report.py
        # and the integration test_protocol_validate.py — this module asserts only the plumbing.
        mocker.patch("pipelex.pipeline.validate_in_process.build_pipe_io_contracts", return_value={})
        mocker.patch("pipelex.pipeline.validate_in_process.build_input_form", return_value={})
        mocker.patch("pipelex.pipeline.validate_in_process.select_primary_blueprint")
        mocker.patch("pipelex.pipeline.validate_in_process.best_effort_graph_spec", new=mocker.AsyncMock(return_value=None))
        mocker.patch("pipelex.pipeline.validate_in_process.build_validation_report")
        return _ValidateEnv(
            validate_bundle_mock=validate_bundle_mock,
            set_current_library_mock=set_current_library_mock,
            clear_current_library_mock=clear_current_library_mock,
            library_manager=library_manager,
        )

    async def test_library_dirs_converted_to_paths_and_allow_signatures_passthrough(self, mocker: MockerFixture) -> None:
        """Constructor library_dirs strings reach validate_bundle as Path objects; allow_signatures forwarded verbatim."""
        env = self._patch_env(mocker, library_ids=[None, "val-lib"])
        runner = PipelexMTHDSProtocol(library_dirs=["dir_alpha", "nested/dir_beta"])

        await runner.validate(mthds_contents=["bundle-content"], allow_signatures=True)

        env.validate_bundle_mock.assert_awaited_once_with(
            mthds_contents=["bundle-content"],
            mthds_sources=None,
            library_dirs=[Path("dir_alpha"), Path("nested/dir_beta")],
            allow_signatures=True,
        )

    async def test_no_library_dirs_passes_none_and_strict_default(self, mocker: MockerFixture) -> None:
        """Without constructor library_dirs, validate_bundle receives None and the strict default."""
        env = self._patch_env(mocker, library_ids=[None, "val-lib"])
        runner = PipelexMTHDSProtocol()

        await runner.validate(mthds_contents=["bundle-content"])

        env.validate_bundle_mock.assert_awaited_once_with(
            mthds_contents=["bundle-content"],
            mthds_sources=None,
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
        """The finally restores the caller's current-library and tears the validation library
        down — unless the validation library IS the caller's library, where it does neither.
        """
        env = self._patch_env(mocker, library_ids=[prev_library_id, validation_library_id])
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
