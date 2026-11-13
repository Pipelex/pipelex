from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex import log
from pipelex.pipeline.direct_bundle_validator import DirectBundleValidator
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.exceptions import RunParameterError
from pipelex.tools.log.log_context import LogContext, get_log_context

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_VALIDATE_IN_PROCESS_NS = "pipelex.pipeline.validate_in_process"
_REQUEST_ID = "01HNJZ4XR7K3Q9D8MWAQ7FY2E5"
_OUTER_REQUEST_ID = "outer-request-id"


class _SweepReachedError(Exception):
    """Raised by the stand-in sweep once it has read the log context, so the test stops there."""


@pytest.mark.asyncio(loop_scope="class")
class TestValidateInProcessRequestId:
    @pytest.mark.parametrize(
        "request_id",
        [
            pytest.param("", id="empty"),
            pytest.param("x" * 129, id="too-long"),
            pytest.param("id with space", id="space"),
            pytest.param("id=forged", id="equals-sign"),
            pytest.param("line\nbreak", id="newline"),
        ],
    )
    async def test_an_invalid_request_id_is_refused_before_the_sweep(self, mocker: MockerFixture, request_id: str) -> None:
        """A request id breaking the rule is the host's bug: refused before the validation library is loaded or the validation timed."""
        sweep = mocker.patch(f"{_VALIDATE_IN_PROCESS_NS}.validate_bundle", new=mocker.AsyncMock())
        validation_report = mocker.patch(f"{_VALIDATE_IN_PROCESS_NS}.MethodValidationReport")

        with pytest.raises(RunParameterError, match="Invalid request_id"):
            await validate_bundles_in_process(mthds_contents=["bundle-content"], request_id=request_id)

        sweep.assert_not_awaited()
        validation_report.assert_not_called()

    async def test_a_valid_request_id_is_bound_on_the_sweeps_log_context(self, mocker: MockerFixture) -> None:
        """The sweep runs with the request id on the log context, and the binding ends with the validation."""
        seen_contexts: list[LogContext | None] = []

        def read_the_log_context(**_kwargs: Any) -> None:
            seen_contexts.append(get_log_context())
            raise _SweepReachedError

        mocker.patch(f"{_VALIDATE_IN_PROCESS_NS}.validate_bundle", new=mocker.AsyncMock(side_effect=read_the_log_context))

        with pytest.raises(_SweepReachedError):
            await validate_bundles_in_process(mthds_contents=["bundle-content"], request_id=_REQUEST_ID)

        assert len(seen_contexts) == 1
        assert seen_contexts[0] is not None
        assert seen_contexts[0].request_id == _REQUEST_ID
        assert get_log_context() is None

    async def test_no_request_id_inherits_the_one_already_bound(self, mocker: MockerFixture) -> None:
        """`None` adds nothing: the id a host bound around the call, as the API's middleware does, stays on the sweep's lines."""
        seen_contexts: list[LogContext | None] = []

        def read_the_log_context(**_kwargs: Any) -> None:
            seen_contexts.append(get_log_context())
            raise _SweepReachedError

        mocker.patch(f"{_VALIDATE_IN_PROCESS_NS}.validate_bundle", new=mocker.AsyncMock(side_effect=read_the_log_context))

        with log.context(request_id=_OUTER_REQUEST_ID), pytest.raises(_SweepReachedError):
            await validate_bundles_in_process(mthds_contents=["bundle-content"], request_id=None)

        assert len(seen_contexts) == 1
        assert seen_contexts[0] is not None
        assert seen_contexts[0].request_id == _OUTER_REQUEST_ID

    async def test_the_direct_validator_refuses_an_invalid_request_id_as_a_fault_not_a_verdict(self, mocker: MockerFixture) -> None:
        """The in-process validator lets the refusal propagate, a no-verdict fault the host answers as its own bug."""
        sweep = mocker.patch(f"{_VALIDATE_IN_PROCESS_NS}.validate_bundle", new=mocker.AsyncMock())

        with pytest.raises(RunParameterError, match="Invalid request_id"):
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
                request_id="not a request id",
            )

        sweep.assert_not_awaited()
