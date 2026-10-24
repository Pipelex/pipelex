from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from mthds.protocol.problem.models import Problem, ProblemItem
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    InvalidLocalSourceError,
    MethodFileTransferError,
    MethodFileTransferOperation,
    MethodFileTransferReason,
    MissingMainStuffError,
    PipelineExecuteTimeoutError,
    RunFailedError,
    RunTimeoutError,
    UploadAuthenticationError,
    UploadTransportError,
    UploadTransportReason,
    run_failed_problem,
)
from pipelex_sdk.runs import RunStatus

from pipelex.errors.unsupported_reasons import LOCAL_FILE_WITH_ADDRESS_DEPENDENCY_UNSUPPORTED_REASON
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.error_rendering import (
    HOSTED_FILE_MISMATCH_NEXT_STEP,
    HOSTED_FILE_REFUSED_NEXT_STEP,
    HOSTED_FILE_STORAGE_ERROR_NEXT_STEP,
    HOSTED_FILE_UNREACHABLE_NEXT_STEP,
    HOSTED_MISSING_KEY_NEXT_STEP,
    HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS,
    HOSTED_UNREACHABLE_NEXT_STEP,
    describe_hosted_error,
    tailored_next_step,
)
from pipelex.hosted.exceptions import (
    HostedLocalFileUploadUnavailableError,
    HostedMethodInvalidError,
    HostedRunInterruptedError,
    HostedRunOutcomeUnknownError,
    HostedRunPollingError,
)
from tests.unit.pipelex.cli.agent_cli.test_data import StoredRunReports
from tests.unit.pipelex.hosted.test_data import HostedRefusals

API_URL = "https://api.test"
#: The request id the hosted edge names in its `X-Request-ID` header.
HEADER_REQUEST_ID = "01M55PHEADER000000000000000"


def _refusal(*, status: int, body: str, route: str = "start", headers: dict[str, str] | None = None) -> ApiResponseError:
    """The error the real client raises when the hosted API answers `route` with this status, body and headers.

    `start` sends `POST /v1/start`, which creates a run; `version` sends `GET /v1/version`, which creates none.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode("utf-8"), headers={"content-type": "application/json", **(headers or {})}, request=request)

    async def _call() -> None:
        client = PipelexAPIClient(api_key="plx_sk_test_not_a_secret", base_url=API_URL)
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        try:
            match route:
                case "start":
                    await client.start(pipe_code="entry", contents={"probe.mthds": 'domain = "probe"\n'})
                case _:
                    await client.version()
        finally:
            await client.close()

    with pytest.raises(ApiResponseError) as exc_info:
        asyncio.run(_call())
    return exc_info.value


def _sent(body: str) -> dict[str, Any]:
    sent: dict[str, Any] = json.loads(body)
    return sent


class TestHostedErrorRendering:
    def test_a_problem_document_is_reported_as_it_came_with_its_items(self) -> None:
        """The runner's own problem gives the code, the domain, the retry verdict, the next step, the request and the items."""
        error = _refusal(status=422, body=HostedRefusals.INVALID_METHOD)

        view = describe_hosted_error(error=error, credential_sent=True)

        problem = view.problem
        assert problem.code == "method.invalid"
        assert problem.effective_domain == "method"
        assert problem.effective_retry == "no"
        assert problem.next_step.kind == "change_method"
        assert problem.next_step.detail == HostedRefusals.INVALID_METHOD_NEXT_STEP
        assert problem.request_id == "01M55PINVALIDMETHOD000000"
        assert problem.errors == [ProblemItem.model_validate(item) for item in HostedRefusals.INVALID_METHOD_ITEMS]
        assert problem.to_wire() == _sent(HostedRefusals.INVALID_METHOD)
        # The problem says it all, where the error's sentence would quote the body.
        assert view.message is None
        assert view.advice is None

    @pytest.mark.parametrize(
        ("status", "body", "headers", "retry_after"),
        [
            (401, HostedRefusals.INVALID_KEY, {}, None),
            (429, HostedRefusals.RATE_LIMITED, {"retry-after": "30"}, 30),
        ],
        ids=["invalid_key", "rate_limited"],
    )
    def test_a_refusal_of_the_hosted_plane_keeps_its_own_reason_and_step(
        self, status: int, body: str, headers: dict[str, str], retry_after: int | None
    ) -> None:
        """A problem document is never read by its status, whether a key was sent or not: its code and its step are its own."""
        error = _refusal(status=status, body=body, headers=headers)

        for credential_sent in (True, False):
            problem = describe_hosted_error(error=error, credential_sent=credential_sent).problem

            sent = _sent(body)
            assert problem.code == sent["code"]
            assert problem.detail == sent["detail"]
            assert problem.next_step.detail == sent["next_step"]["detail"]
            assert problem.effective_retry == sent["retry"]
            assert problem.retry_after == retry_after

    @pytest.mark.parametrize(
        ("status", "body", "route", "credential_sent", "code", "next_step"),
        [
            (401, HostedRefusals.BARE_UNAUTHORIZED, "start", True, "auth.invalid_credential", HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[401]),
            (401, HostedRefusals.BARE_UNAUTHORIZED, "start", False, "auth.missing_credential", HOSTED_MISSING_KEY_NEXT_STEP),
            (403, HostedRefusals.BARE_FORBIDDEN, "start", True, "auth.invalid_credential", HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[403]),
            (403, HostedRefusals.BARE_FORBIDDEN, "start", False, "auth.missing_credential", HOSTED_MISSING_KEY_NEXT_STEP),
            # A start a server answers with a bare 404 is a bare runner's, which pipelex-sdk raises as its own error.
            (404, HostedRefusals.BARE_NOT_FOUND, "version", True, "request.not_found", HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[404]),
        ],
        ids=["unauthorized_with_key", "unauthorized_without_key", "forbidden_with_key", "forbidden_without_key", "not_found"],
    )
    def test_a_bare_answer_of_the_edge_reads_by_its_status_and_the_key_sent(
        self, status: int, body: str, route: str, credential_sent: bool, code: str, next_step: str
    ) -> None:
        """An answer that is no problem document reads by its status, a refused credential as a missing one when no key was
        sent, with the next step that names this client's settings and the request id the edge's header gives.
        """
        error = _refusal(status=status, body=body, route=route, headers={"x-request-id": HEADER_REQUEST_ID})

        view = describe_hosted_error(error=error, credential_sent=credential_sent)

        problem = view.problem
        assert problem.code == code
        assert problem.status == status
        assert problem.next_step.detail == next_step
        assert problem.request_id == HEADER_REQUEST_ID
        assert view.message is None

    @pytest.mark.parametrize(("status", "named"), [(401, PIPELEX_API_KEY_ENV_KEY), (403, PIPELEX_API_KEY_ENV_KEY), (404, PIPELEX_BASE_URL_ENV_KEY)])
    def test_the_status_steps_name_the_hosted_settings(self, status: int, named: str) -> None:
        assert named in HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[status]
        assert "MTHDS_" not in HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[status]

    @pytest.mark.parametrize("status", [502, 503, 500])
    def test_a_bare_server_fault_on_the_run_request_leaves_the_outcome_unknown(self, status: int) -> None:
        """A 5xx on the run request may follow a run that started, so it keeps the client's reading, and its step reads the run."""
        error = _refusal(status=status, body=HostedRefusals.GATEWAY_PAGE)

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == "client.outcome_unknown"
        assert problem.effective_retry == "outcome_unknown"
        assert problem.next_step.kind == "read_run"

    @pytest.mark.parametrize(
        ("status", "body", "code", "retry"),
        [
            (400, HostedRefusals.BARE_BAD_REQUEST, "client.response_unreadable", "no"),
            (503, HostedRefusals.GATEWAY_PAGE, "runtime.unavailable", "yes"),
            (429, HostedRefusals.BARE_BAD_REQUEST, "runtime.unavailable", "yes"),
        ],
        ids=["bad_request", "unavailable", "throttled"],
    )
    def test_any_other_bare_answer_keeps_the_client_s_reading_and_its_code_s_step(self, status: int, body: str, code: str, retry: str) -> None:
        """A status this client does not read itself keeps pipelex-sdk's reading, whose code gives the next step."""
        error = _refusal(status=status, body=body, route="version")

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == code
        assert problem.effective_retry == retry
        assert problem.next_step.detail == error.problem.next_step.detail

    def test_an_unreachable_api_names_the_base_url_settings(self) -> None:
        error = ApiUnreachableError("Could not reach Pipelex API at https://api.test (ConnectError)", api_url=API_URL, network_code="ConnectError")

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.code == "client.unreachable"
        assert view.problem.effective_retry == "yes"
        assert view.problem.next_step.kind == "retry"
        assert view.problem.next_step.detail == HOSTED_UNREACHABLE_NEXT_STEP
        assert "--base-url" in view.problem.next_step.detail
        assert PIPELEX_BASE_URL_ENV_KEY in view.problem.next_step.detail
        assert view.message is None

    def test_a_run_request_that_may_have_left_keeps_its_code_s_step(self) -> None:
        """A request that may have created a run is never told to check the network and run again."""
        error = ApiUnreachableError("Lost the connection", api_url=API_URL, network_code="ReadError", may_start_run=True)

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == "client.outcome_unknown"
        assert problem.next_step.detail != HOSTED_UNREACHABLE_NEXT_STEP
        assert tailored_next_step(error=error) is None

    @pytest.mark.parametrize(
        ("run_error", "expected_code"),
        [
            (StoredRunReports.PROBLEM, "pipe.output_multiplicity"),
            (StoredRunReports.PROBLEM_WITH_REPORT_MEMBERS, "pipe.output_multiplicity"),
        ],
        ids=["problem", "problem_with_report_members"],
    )
    def test_a_failed_run_nests_its_own_problem_in_the_caller_s_view(self, run_error: dict[str, Any], expected_code: str) -> None:
        """The run's stored record is its operator's: it is projected onto the caller's view, its diagnostics and the members
        no reader declares left out, and the run's code, domain and retry verdict kept.
        """
        error = RunFailedError(
            "Run finished with status FAILED: the branches do not combine",
            run_id="run_9",
            status=RunStatus.FAILED,
            problem=run_failed_problem(run_id="run_9", status=RunStatus.FAILED, run_error=Problem.model_validate(run_error)),
        )

        view = describe_hosted_error(error=error, credential_sent=True)

        problem = view.problem
        assert problem.code == "run.failed"
        assert problem.pipeline_run_id == "run_9"
        assert problem.effective_retry == "no"
        assert problem.run_error is not None
        assert problem.run_error.code == expected_code
        assert problem.run_error.effective_domain == "method"
        assert problem.run_error.diagnostics is None
        assert "error_type" not in problem.run_error.to_wire()
        assert view.message == "Run finished with status FAILED: the branches do not combine"

    def test_a_failed_run_without_a_stored_problem_still_names_the_run(self) -> None:
        error = RunFailedError("Run finished with status CANCELLED", run_id="run_9", status=RunStatus.CANCELLED)

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == "run.failed"
        assert problem.pipeline_run_id == "run_9"
        assert problem.run_error is None
        assert tailored_next_step(error=error) is None

    @pytest.mark.parametrize(
        "error",
        [
            RunTimeoutError("Run 'run_7' did not finish within 1200s", run_id="run_7", timeout_seconds=1200.0),
            MissingMainStuffError("Completed run 'run_7' returned no main stuff", run_id="run_7"),
            HostedRunPollingError("The run run_7 started on the hosted API, but following it failed", pipeline_run_id="run_7"),
        ],
    )
    def test_an_error_after_the_start_names_the_run(self, error: Exception) -> None:
        assert isinstance(error, (RunTimeoutError, MissingMainStuffError, HostedRunPollingError))
        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.pipeline_run_id == "run_7"
        assert "run_7" in view.problem.next_step.detail
        assert view.message is not None
        assert "run_7" in view.message

    def test_a_lost_run_is_not_reported_as_a_network_failure(self) -> None:
        error = HostedRunPollingError("The run run_7 started on the hosted API, but following it failed", pipeline_run_id="run_7")

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.code == "client.follow_failed"
        assert view.problem.effective_domain == "runtime"
        assert view.problem.effective_retry == "outcome_unknown"
        assert view.advice is not None
        assert "may still be running" in view.advice

    def test_an_unreadable_local_file_names_the_path_to_check(self) -> None:
        error = InvalidLocalSourceError('Local file cannot be read: "inputs/missing.pdf" (FileNotFoundError).', source="inputs/missing.pdf")

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.effective_domain == "input"
        assert view.message is not None
        assert "inputs/missing.pdf" in view.message
        assert "inputs" in view.problem.next_step.detail

    def test_a_refused_upload_points_at_the_key(self) -> None:
        error = UploadAuthenticationError('Upload of "invoice.pdf" was not authorized (401). Check the configured Pipelex API key.', status=401)

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.effective_domain == "account"
        assert PIPELEX_API_KEY_ENV_KEY in problem.next_step.detail

    def test_an_upload_that_could_not_reach_the_api_points_at_the_network_and_the_origin(self) -> None:
        unreachable = ApiUnreachableError(
            "Could not reach Pipelex API at https://api.test (ConnectError)", api_url=API_URL, network_code="ConnectError"
        )
        error = UploadTransportError(
            'Upload of "a.pdf" could not reach the Pipelex API (ConnectError).', reason=UploadTransportReason.UNREACHABLE, cause=unreachable
        )

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == "client.unreachable"
        assert PIPELEX_BASE_URL_ENV_KEY in problem.next_step.detail
        assert "network" in problem.next_step.detail

    def test_an_upload_the_server_failed_keeps_its_code_s_step(self) -> None:
        error = UploadTransportError('Upload of "a.pdf" failed (502): Bad Gateway.', status=502, reason=UploadTransportReason.SERVER_ERROR)

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == "runtime.unavailable"
        assert problem.effective_retry == "yes"
        assert problem.next_step.detail == error.problem.next_step.detail

    @pytest.mark.parametrize(
        ("reason", "status", "code", "retry", "next_step"),
        [
            (MethodFileTransferReason.UNREACHABLE, None, "runtime.unavailable", "yes", HOSTED_FILE_UNREACHABLE_NEXT_STEP),
            (MethodFileTransferReason.STORAGE_ERROR, 503, "runtime.unavailable", "yes", HOSTED_FILE_STORAGE_ERROR_NEXT_STEP),
            (MethodFileTransferReason.STORAGE_ERROR, 429, "runtime.unavailable", "yes", HOSTED_FILE_STORAGE_ERROR_NEXT_STEP),
            (MethodFileTransferReason.MISMATCH, None, "client.response_unreadable", "no", HOSTED_FILE_MISMATCH_NEXT_STEP),
            (MethodFileTransferReason.REFUSED, 403, "client.response_unreadable", "no", HOSTED_FILE_REFUSED_NEXT_STEP),
        ],
        ids=["unreachable", "storage_failed", "storage_throttled", "mismatch", "refused"],
    )
    def test_a_file_of_the_tree_that_could_not_be_moved_carries_the_sdk_s_verdict(
        self, reason: MethodFileTransferReason, status: int | None, code: str, retry: str, next_step: str
    ) -> None:
        """A tree sent by hash uploads what the hosted API lacks before the request: nothing started, and whether running
        again helps is the SDK's problem, every reason but a refusal and a mismatch, which are reported.
        """
        error = MethodFileTransferError(
            "Uploading the file with SHA-256 abc to storage.test failed, so the run was not started.",
            operation=MethodFileTransferOperation.UPLOAD,
            reason=reason,
            sha256="abc",
            status=status,
        )

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.message == "Uploading the file with SHA-256 abc to storage.test failed, so the run was not started."
        assert view.problem.code == code
        assert view.problem.effective_retry == retry
        assert view.problem.next_step.detail == next_step
        assert tailored_next_step(error=error) == next_step

    def test_a_method_that_does_not_load_lists_the_verdict_s_items(self) -> None:
        items = [ProblemItem.model_validate(item) for item in HostedRefusals.INVALID_METHOD_ITEMS]
        error = HostedMethodInvalidError("The hosted API cannot load the method: Bundle does not load", errors=items)

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.code == "method.invalid"
        assert view.problem.effective_domain == "method"
        assert view.problem.errors == items
        assert view.problem.pipeline_run_id is None
        assert view.message == "The hosted API cannot load the method: Bundle does not load"
        assert view.advice == "Fix the method as each of its errors says, then run it again"

    def test_an_interrupted_wait_names_the_run_that_keeps_going(self) -> None:
        view = describe_hosted_error(error=HostedRunInterruptedError(pipeline_run_id="run_7"), credential_sent=True)

        assert view.problem.code == "client.follow_failed"
        assert view.problem.pipeline_run_id == "run_7"
        assert view.message is not None
        assert "keeps going" in view.message
        assert view.advice is not None
        assert "run_7" in view.advice

    def test_an_interruption_before_the_acknowledgement_points_at_the_run_history(self) -> None:
        view = describe_hosted_error(error=HostedRunInterruptedError(pipeline_run_id=None), credential_sent=True)

        assert view.problem.code == "client.outcome_unknown"
        assert view.problem.pipeline_run_id is None
        assert view.advice is not None
        assert "run history" in view.advice

    def test_a_start_lost_after_it_was_sent_points_at_the_run_history(self) -> None:
        error = HostedRunOutcomeUnknownError("The connection to the hosted API failed after the run request was sent (ReadError: reset)")

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.code == "client.outcome_unknown"
        assert view.problem.effective_retry == "outcome_unknown"
        assert view.problem.pipeline_run_id is None
        assert view.advice is not None
        assert "run history" in view.advice
        assert "network" not in view.problem.next_step.detail

    def test_a_local_file_for_a_method_with_an_address_dependency_points_at_a_url(self) -> None:
        error = HostedLocalFileUploadUnavailableError(
            "Local file upload is not available yet for methods with address-based dependencies, and the inputs name a local file"
        )

        view = describe_hosted_error(error=error, credential_sent=True)

        assert view.problem.code == "request.unsupported"
        assert view.problem.as_wire()["params"] == {"field": "inputs", "reason": LOCAL_FILE_WITH_ADDRESS_DEPENDENCY_UNSUPPORTED_REASON}
        assert view.problem.effective_domain == "input"
        assert view.advice is not None
        assert "https URL" in view.advice

    def test_a_blocking_route_timeout_warns_that_the_run_may_still_be_going(self) -> None:
        """Only a server that keeps no runs is called on the blocking route, so running again takes the same route and repeats a paid run."""
        error = PipelineExecuteTimeoutError("POST /v1/execute was cut off after 31s", elapsed_seconds=31.0)

        problem = describe_hosted_error(error=error, credential_sent=True).problem

        assert problem.code == "client.outcome_unknown"
        assert problem.effective_retry == "outcome_unknown"
        assert "run it again" not in problem.next_step.detail
        assert "may still be going" in problem.next_step.detail
        assert PIPELEX_BASE_URL_ENV_KEY in problem.next_step.detail
