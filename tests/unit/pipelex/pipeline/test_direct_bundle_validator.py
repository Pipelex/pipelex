"""The core in-process bundle validator wraps ``validate_bundles_in_process`` as verdict-as-value.

Pins the wrapper's two branches with the in-process sweep mocked out (its own report shaping is
covered by test_validation_report.py / the integration test_protocol_validate.py): a successful
sweep is returned verbatim as the valid arm; a ``ValidateBundleError`` is converted to its
structured ``ErrorReport`` (the invalid arm) rather than propagated. Also pins argument
passthrough, including the ``library_dirs`` host context and the ``log_context`` label.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.base_exceptions import ErrorReport
from pipelex.pipeline.direct_bundle_validator import DirectBundleValidator
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestDirectBundleValidator:
    async def test_valid_sweep_is_returned_as_the_valid_arm(self, mocker: MockerFixture) -> None:
        """A successful in-process sweep's report is returned verbatim, with arguments forwarded."""
        report = mocker.MagicMock(name="validation_report")
        in_process_mock = mocker.patch(
            "pipelex.pipeline.direct_bundle_validator.validate_bundles_in_process",
            new=mocker.AsyncMock(return_value=report),
        )

        verdict = await DirectBundleValidator().validate_bundles(
            mthds_contents=["bundle-content"],
            mthds_sources=["domain.mthds"],
            allow_signatures=True,
            library_dirs=[Path("lib_dir")],
        )

        assert verdict is report
        in_process_mock.assert_awaited_once_with(
            mthds_contents=["bundle-content"],
            mthds_sources=["domain.mthds"],
            library_dirs=[Path("lib_dir")],
            allow_signatures=True,
            log_context="API validate",
        )

    async def test_validate_bundle_error_becomes_the_invalid_arm(self, mocker: MockerFixture) -> None:
        """An invalid bundle's ValidateBundleError is converted to its ErrorReport, not propagated."""
        error = ValidateBundleError("bundle is invalid")
        mocker.patch(
            "pipelex.pipeline.direct_bundle_validator.validate_bundles_in_process",
            new=mocker.AsyncMock(side_effect=error),
        )

        verdict = await DirectBundleValidator().validate_bundles(
            mthds_contents=["bundle-content"],
            mthds_sources=None,
            allow_signatures=False,
            library_dirs=None,
        )

        assert isinstance(verdict, ErrorReport)
        assert verdict.error_type == ValidateBundleError.__name__
        assert verdict == error.to_error_report()

    async def test_other_errors_propagate_as_no_verdict_faults(self, mocker: MockerFixture) -> None:
        """A non-ValidateBundleError (a genuine infra fault) propagates — the host maps it to a 5xx."""
        mocker.patch(
            "pipelex.pipeline.direct_bundle_validator.validate_bundles_in_process",
            new=mocker.AsyncMock(side_effect=RuntimeError("library teardown blew up")),
        )

        with pytest.raises(RuntimeError, match="library teardown blew up"):
            await DirectBundleValidator().validate_bundles(
                mthds_contents=["bundle-content"],
                mthds_sources=None,
                allow_signatures=False,
                library_dirs=None,
            )
