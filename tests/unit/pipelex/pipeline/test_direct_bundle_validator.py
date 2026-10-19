"""The core in-process bundle validator wraps ``validate_bundles_in_process`` as verdict-as-value.

Pins the wrapper's two branches with the in-process sweep mocked out (its own report shaping is
covered by test_validation_report.py / the integration test_protocol_validate.py): a successful
sweep is returned verbatim as the valid arm; a ``ValidateBundleError`` is converted to a
``BundleValidationFailure`` (the invalid arm: its problem in the operator's view, and its validation
items) rather than propagated. Also pins argument
passthrough, including the ``library_dirs`` host context, the explicit ``graph_pipe_code`` target
and the ``log_context`` label, and that the read scope stops here: the in-process arm reads every
file in its own process, through no blob store, so the sweep is never handed one.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.direct_bundle_validator import DirectBundleValidator
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.caller_identity import CallerIdentity

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestDirectBundleValidator:
    async def test_valid_sweep_is_returned_as_the_valid_arm(self, mocker: MockerFixture) -> None:
        """A successful in-process sweep's report is returned verbatim, with arguments forwarded."""
        report = mocker.MagicMock(name="validation_report")
        submitted_files = {"invoice.docx": b"docx bytes"}
        in_process_mock = mocker.patch(
            "pipelex.pipeline.direct_bundle_validator.validate_bundles_in_process",
            new=mocker.AsyncMock(return_value=report),
        )

        verdict = await DirectBundleValidator().validate_bundles(
            mthds_contents=["bundle-content"],
            mthds_sources=["domain.mthds"],
            allow_signatures=True,
            library_dirs=[Path("lib_dir")],
            caller_identity=CallerIdentity(user_id="user-42", extras={"organization": "org_acme"}),
            graph_pipe_code="extract_document_markdown",
            submitted_files=submitted_files,
            method_dir=None,
            methods_dirs=None,
            read_scope="org_acme",
        )

        assert verdict is report
        in_process_mock.assert_awaited_once_with(
            mthds_contents=["bundle-content"],
            mthds_sources=["domain.mthds"],
            library_dirs=[Path("lib_dir")],
            allow_signatures=True,
            graph_pipe_code="extract_document_markdown",
            log_context="API validate",
            caller_identity=CallerIdentity(user_id="user-42", extras={"organization": "org_acme"}),
            submitted_files=submitted_files,
            method_dir=None,
            methods_dirs=None,
        )

    @pytest.mark.builds_problems_without_required_params(
        reason="a message-only verdict's residual item names no declaration, so it carries no field path"
    )
    async def test_validate_bundle_error_becomes_the_invalid_arm(self, mocker: MockerFixture) -> None:
        """An invalid bundle's ValidateBundleError is converted to the invalid arm, its operator's problem and its items, not propagated."""
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
            caller_identity=None,
            graph_pipe_code=None,
            submitted_files=None,
            method_dir=None,
            methods_dirs=None,
            read_scope=None,
        )

        assert isinstance(verdict, BundleValidationFailure)
        assert verdict.problem == error.to_problem(view=ProblemView.OPERATOR)
        assert verdict.problem.code == CoreCode.METHOD_INVALID
        assert verdict.problem.diagnostics is not None
        assert verdict.problem.diagnostics.error_class == ValidateBundleError.__name__
        assert verdict.validation_errors == error.validation_error_items()

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
                caller_identity=None,
                graph_pipe_code=None,
                submitted_files=None,
                method_dir=None,
                methods_dirs=None,
                read_scope=None,
            )
