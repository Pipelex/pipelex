from __future__ import annotations

import asyncio

import httpx
import pytest
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    InvalidLocalSourceError,
    MissingMainStuffError,
    RunFailedError,
    RunTimeoutError,
    UploadAuthenticationError,
    UploadTransportError,
)
from pipelex_sdk.runs import RunStatus
from pipelex_sdk.validation_models import ValidationErrorItem

from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.error_rendering import (
    HOSTED_REFUSAL_CALLER_NEXT_STEP,
    HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS,
    HOSTED_SERVER_FAULT_NEXT_STEP,
    describe_hosted_error,
    hosted_refusal_next_step,
)
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunPollingError
from tests.unit.pipelex.hosted.test_data import HostedRefusals

API_URL = "https://api.test"
LABELLED_ITEM = ValidationErrorItem.model_validate(
    {"category": "blueprint_validation", "message": "unknown concept Foo", "source": "lib/b.mthds", "pipe_code": "step2"}
)


def _refusal(*, status: int, body: str) -> ApiResponseError:
    """The error the real client raises when the hosted API answers `POST /v1/start` with this status and body."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode("utf-8"), headers={"content-type": "application/problem+json"}, request=request)

    async def _start() -> None:
        client = PipelexAPIClient(api_key="plx_sk_test_not_a_secret", base_url=API_URL)
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        try:
            await client.start(pipe_code="entry", mthds_contents=['domain = "probe"\n'])
        finally:
            await client.close()

    with pytest.raises(ApiResponseError) as exc_info:
        asyncio.run(_start())
    return exc_info.value


class TestHostedErrorRendering:
    def test_a_refusal_with_a_next_step_keeps_the_runner_reason_and_its_advice(self) -> None:
        error = _refusal(status=422, body=HostedRefusals.INVALID_BUNDLE)

        view = describe_hosted_error(error=error)

        assert view.error_type == "ValidateBundleError"
        assert view.message == f"API POST /v1/start failed (422): {HostedRefusals.INVALID_BUNDLE_DETAIL}"
        assert view.next_step == HostedRefusals.INVALID_BUNDLE_NEXT_STEP
        assert hosted_refusal_next_step(error=error) == HostedRefusals.INVALID_BUNDLE_NEXT_STEP

    def test_a_refused_key_points_at_the_pipelex_api_key(self) -> None:
        """The platform's own 401 advises nothing; the next step names the variable that holds the key."""
        error = _refusal(status=401, body=HostedRefusals.UNAUTHORIZED)

        view = describe_hosted_error(error=error)

        assert view.error_type == "ApiResponseError"
        assert view.message == f"API POST /v1/start failed (401): {HostedRefusals.UNAUTHORIZED_DETAIL}"
        assert view.next_step == HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[401]
        assert PIPELEX_API_KEY_ENV_KEY in view.next_step

    @pytest.mark.parametrize(("status", "named"), [(401, PIPELEX_API_KEY_ENV_KEY), (403, PIPELEX_API_KEY_ENV_KEY), (404, PIPELEX_BASE_URL_ENV_KEY)])
    def test_the_status_hints_name_the_hosted_settings(self, status: int, named: str) -> None:
        assert named in HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[status]
        assert "MTHDS_" not in HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[status]

    @pytest.mark.parametrize(
        ("status", "expected_next_step"),
        [(400, HOSTED_REFUSAL_CALLER_NEXT_STEP), (500, HOSTED_SERVER_FAULT_NEXT_STEP)],
    )
    def test_an_unadvised_refusal_without_a_hint_of_its_own_falls_back_by_status_class(self, status: int, expected_next_step: str) -> None:
        error = _refusal(status=status, body=HostedRefusals.SERVER_FAULT)
        assert hosted_refusal_next_step(error=error) == expected_next_step

    def test_an_unreachable_api_names_the_base_url_settings(self) -> None:
        error = ApiUnreachableError("Could not reach Pipelex API at https://api.test (ConnectError)", api_url=API_URL, code="ConnectError")

        view = describe_hosted_error(error=error)

        assert view.error_type == "ApiUnreachableError"
        assert view.message == "Could not reach Pipelex API at https://api.test (ConnectError)"
        assert "--base-url" in view.next_step
        assert PIPELEX_BASE_URL_ENV_KEY in view.next_step

    def test_a_failed_run_reports_the_runner_class_and_its_advice(self) -> None:
        report = RunErrorReport.model_validate(
            {
                "error_type": "LLMCompletionError",
                "message": "The provider refused the prompt",
                "error_domain": "runtime",
                "user_action": {"kind": "wait_and_retry", "detail": "Run it again in a minute"},
            }
        )
        error = RunFailedError(
            "Run finished with status FAILED: The provider refused the prompt", run_id="run_9", status=RunStatus.FAILED, error=report
        )

        view = describe_hosted_error(error=error)

        assert view.error_type == "LLMCompletionError"
        assert view.message == "Run finished with status FAILED: The provider refused the prompt"
        assert view.next_step == "Run it again in a minute"

    def test_a_failed_run_without_a_report_still_names_the_run(self) -> None:
        error = RunFailedError("Run finished with status CANCELLED", run_id="run_9", status=RunStatus.CANCELLED, error=None)

        view = describe_hosted_error(error=error)

        assert view.error_type == "RunFailedError"
        assert "run_9" in view.next_step

    def test_a_run_past_the_wait_keeps_going_and_says_where(self) -> None:
        error = RunTimeoutError("Run 'run_7' did not finish within 1200s", run_id="run_7", timeout_seconds=1200.0)

        view = describe_hosted_error(error=error)

        assert view.error_type == "RunTimeoutError"
        assert "run_7" in view.next_step

    def test_an_unreadable_local_file_names_the_path_to_check(self) -> None:
        error = InvalidLocalSourceError('Local file cannot be read: "inputs/missing.pdf" (FileNotFoundError).', source="inputs/missing.pdf")

        view = describe_hosted_error(error=error)

        assert view.error_type == "InvalidLocalSourceError"
        assert view.error_domain == "input"
        assert "inputs/missing.pdf" in view.message
        assert "inputs" in view.next_step

    def test_a_refused_upload_points_at_the_key(self) -> None:
        error = UploadAuthenticationError('Upload of "invoice.pdf" was not authorized (401). Check the configured Pipelex API key.', status=401)

        view = describe_hosted_error(error=error)

        assert PIPELEX_API_KEY_ENV_KEY in view.next_step

    def test_an_upload_that_could_not_reach_the_api_points_at_the_network_and_the_origin(self) -> None:
        unreachable = ApiUnreachableError("Could not reach Pipelex API at https://api.test (ConnectError)", api_url=API_URL, code="ConnectError")
        error = UploadTransportError('Upload of "a.pdf" could not reach the Pipelex API (ConnectError).')
        error.__cause__ = unreachable

        view = describe_hosted_error(error=error)

        assert view.error_type == "UploadTransportError"
        assert view.error_domain == "config"
        assert PIPELEX_BASE_URL_ENV_KEY in view.next_step
        assert "network" in view.next_step

    def test_an_upload_the_server_failed_is_a_server_fault(self) -> None:
        error = UploadTransportError('Upload of "a.pdf" failed (502): Bad Gateway.')

        view = describe_hosted_error(error=error)

        assert view.next_step == HOSTED_SERVER_FAULT_NEXT_STEP
        assert view.error_domain == "runtime"

    def test_a_failed_run_carries_its_id_and_its_validation_items(self) -> None:
        report = RunErrorReport.model_validate(
            {"error_type": "ValidateBundleError", "message": "bundle invalid", "validation_errors": [LABELLED_ITEM.model_dump(mode="json")]}
        )
        error = RunFailedError("Run finished with status FAILED: bundle invalid", run_id="run_9", status=RunStatus.FAILED, error=report)

        view = describe_hosted_error(error=error)

        assert view.pipeline_run_id == "run_9"
        assert view.validation_errors == (LABELLED_ITEM,)

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
        view = describe_hosted_error(error=error)

        assert view.pipeline_run_id == "run_7"
        assert "run_7" in view.next_step

    def test_a_lost_run_is_not_reported_as_a_network_failure(self) -> None:
        error = HostedRunPollingError("The run run_7 started on the hosted API, but following it failed", pipeline_run_id="run_7")

        view = describe_hosted_error(error=error)

        assert view.error_type == "HostedRunPollingError"
        assert view.error_domain == "runtime"
        assert "may still be running" in view.next_step

    def test_a_method_that_does_not_load_carries_its_labelled_items(self) -> None:
        error = HostedMethodInvalidError("The hosted API cannot load the method: Bundle does not load", validation_errors=[LABELLED_ITEM])

        view = describe_hosted_error(error=error)

        assert view.error_type == "HostedMethodInvalidError"
        assert view.error_domain == "input"
        assert view.validation_errors == (LABELLED_ITEM,)
        assert view.pipeline_run_id is None
