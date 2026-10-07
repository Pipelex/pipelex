from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mthds.protocol.input_form import PipeInputFormDescriptor
from mthds.protocol.models import VersionInfo
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.crate_models import CrateInvalidReport, MthdsFileItem, PipeIORequest, PipeIOValidReport
from pipelex_sdk.errors import (
    ApiUnreachableError,
    MissingMainStuffError,
    RunFailedError,
    RunLifecycleUnavailableError,
    RunTimeoutError,
)
from pipelex_sdk.prepare_inputs import PreparedInputs
from pipelex_sdk.runs import PipelexRunResultStart, RunResults, RunStatus
from pipelex_sdk.upload import UploadRecord
from pipelex_sdk.validation_models import ValidationErrorItem
from pydantic import ValidationError

from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunPollingError
from pipelex.hosted.hosted_run import HostedRunRequest, run_hosted
from tests.unit.pipelex.hosted.test_data import HostedDescriptors, HostedVersions

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

BUNDLE_FILE = MthdsFileItem(content='domain = "probe"\n', source="probe.mthds")
DOCUMENT_METHOD_REF = "github.com/Pipelex/methods/documents@v0.1.7"
HOSTED_RUN_MODULE = "pipelex.hosted.hosted_run"
RUN_ID = "run_1"
DONE = RunResults(pipeline_run_id=RUN_ID, main_stuff={"text": "done"})


def _valid_report(*, pipe_ref: str, descriptor_json: str) -> PipeIOValidReport:
    """A pipe-io valid arm carrying the one descriptor this module reads; the other artifacts play no part here."""
    descriptor = PipeInputFormDescriptor.model_validate_json(descriptor_json)
    return PipeIOValidReport.model_construct(
        is_valid=True,
        pipe_ref=pipe_ref,
        pipe_io_contracts={},
        input_form={pipe_ref: descriptor},
        output_form={},
        default_pipe_ref=pipe_ref,
        pending_signatures=[],
        is_runnable=True,
    )


def _mocked_client(
    mocker: MockerFixture, *, pipe_io_report: PipeIOValidReport | CrateInvalidReport | None = None, version: str = HostedVersions.HOSTED
) -> MagicMock:
    """A client whose handshake names `version`, whose start is acknowledged as `RUN_ID`, and whose run completes."""
    client: MagicMock = mocker.create_autospec(PipelexAPIClient, instance=True)
    client.base_url = "https://hosted.test"
    client.version.return_value = VersionInfo.model_validate_json(version)
    client.start.return_value = PipelexRunResultStart(pipeline_run_id=RUN_ID)
    client.wait_for_result.return_value = DONE
    if pipe_io_report is not None:
        client.pipe_io.return_value = pipe_io_report
    return client


class TestHostedRun:
    @pytest.mark.asyncio
    async def test_an_inline_bundle_without_inputs_starts_and_waits_on_its_contents(self, mocker: MockerFixture) -> None:
        """A local bundle travels as `mthds_contents`, and with no inputs nothing is asked of pipe-io."""
        client = _mocked_client(mocker)
        request = HostedRunRequest(mthds_files=[BUNDLE_FILE], pipe_code="entry", dynamic_output_concept_ref="probe.Thing")

        outcome = await run_hosted(client=client, request=request)

        client.start.assert_awaited_once_with(
            pipe_code="entry",
            mthds_contents=[BUNDLE_FILE.content],
            inputs=None,
            dynamic_output_concept_ref="probe.Thing",
            method_ref=None,
            method_id=None,
        )
        client.wait_for_result.assert_awaited_once_with(RUN_ID)
        client.pipe_io.assert_not_awaited()
        client.prepare_inputs.assert_not_awaited()
        assert outcome.results.pipeline_run_id == "run_1"
        assert outcome.results.main_stuff == {"text": "done"}
        assert outcome.uploads == []
        assert outcome.pipe_ref is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("source", "expected_method_ref", "expected_method_id"),
        [
            ({"method_ref": DOCUMENT_METHOD_REF}, DOCUMENT_METHOD_REF, None),
            ({"method_id": "mt_abc123"}, None, "mt_abc123"),
        ],
    )
    async def test_a_remote_source_is_named_not_sent(
        self,
        mocker: MockerFixture,
        source: dict[str, str],
        expected_method_ref: str | None,
        expected_method_id: str | None,
    ) -> None:
        """A published address and a stored method are resolved by the hosted API: no content leaves this machine."""
        client = _mocked_client(mocker)
        request = HostedRunRequest.model_validate(source)

        await run_hosted(client=client, request=request)

        client.start.assert_awaited_once_with(
            pipe_code=None,
            mthds_contents=None,
            inputs=None,
            dynamic_output_concept_ref=None,
            method_ref=expected_method_ref,
            method_id=expected_method_id,
        )

    @pytest.mark.asyncio
    async def test_inputs_naming_no_local_file_are_sent_as_they_are(self, mocker: MockerFixture) -> None:
        """The signature says where files sit; inputs with none there need no preparation."""
        report = _valid_report(pipe_ref=HostedDescriptors.TEXT_ONLY_PIPE_REF, descriptor_json=HostedDescriptors.TEXT_ONLY)
        client = _mocked_client(mocker, pipe_io_report=report)
        inputs = {"text": "report.pdf is a word here, not a file"}
        request = HostedRunRequest(method_ref="github.com/Pipelex/methods/text_stats@v0.1.7", inputs=inputs)

        outcome = await run_hosted(client=client, request=request)

        client.pipe_io.assert_awaited_once_with(PipeIORequest(method_ref="github.com/Pipelex/methods/text_stats@v0.1.7"))
        client.prepare_inputs.assert_not_awaited()
        assert client.start.await_args.kwargs["inputs"] == inputs
        assert outcome.pipe_ref == HostedDescriptors.TEXT_ONLY_PIPE_REF

    @pytest.mark.asyncio
    async def test_a_local_file_is_anchored_then_uploaded_before_the_run(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A relative file path resolves against the inputs file's directory, is uploaded, and the run gets the storage URI."""
        report = _valid_report(pipe_ref=HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF, descriptor_json=HostedDescriptors.MIXED_FILE_POSITIONS)
        client = _mocked_client(mocker, pipe_io_report=report)
        prepared_inputs: dict[str, Any] = {"document": {"url": "pipelex-storage://uploads/abc.pdf"}, "notes": "see attached"}
        upload = UploadRecord(uri="pipelex-storage://uploads/abc.pdf", filename="invoice.pdf", content_type="application/pdf", size=3)
        client.prepare_inputs.return_value = PreparedInputs(inputs=prepared_inputs, uploads=[upload])
        request = HostedRunRequest(
            mthds_files=[BUNDLE_FILE],
            pipe_code="summarize_report",
            inputs={"document": "docs/invoice.pdf", "notes": "see attached"},
            inputs_base_dir=tmp_path,
        )

        outcome = await run_hosted(client=client, request=request)

        client.pipe_io.assert_awaited_once_with(PipeIORequest(files=[BUNDLE_FILE], pipe_ref="summarize_report"))
        client.prepare_inputs.assert_awaited_once_with(
            files=[BUNDLE_FILE],
            method_ref=None,
            method_id=None,
            pipe_ref=HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF,
            inputs={"document": str(tmp_path / "docs" / "invoice.pdf"), "notes": "see attached"},
        )
        assert client.start.await_args.kwargs["inputs"] == prepared_inputs
        assert outcome.uploads == [upload]
        assert outcome.pipe_ref == HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF

    @pytest.mark.asyncio
    async def test_a_method_that_does_not_load_is_refused_before_the_run_with_its_labelled_items(self, mocker: MockerFixture) -> None:
        """pipe-io's verdict names each file by the label it was sent under; `/v1/start` takes bare contents and could not."""
        item = ValidationErrorItem.model_validate(
            {"category": "blueprint_validation", "message": "unknown concept Foo", "source": "lib/b.mthds", "pipe_code": "step2"}
        )
        invalid = CrateInvalidReport(is_valid=False, validation_errors=[item], message="Bundle does not load")
        client = _mocked_client(mocker, pipe_io_report=invalid)
        request = HostedRunRequest(mthds_files=[BUNDLE_FILE], inputs={"document": "invoice.pdf"})

        with pytest.raises(HostedMethodInvalidError) as exc_info:
            await run_hosted(client=client, request=request)

        assert exc_info.value.validation_errors == [item]
        assert "Bundle does not load" in exc_info.value.message
        client.prepare_inputs.assert_not_awaited()
        client.start.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "follow_error",
        [
            ApiUnreachableError(
                "Could not reach Pipelex API at https://hosted.test (ConnectError)", api_url="https://hosted.test", code="ConnectError"
            ),
            httpx.RemoteProtocolError("server disconnected"),
        ],
    )
    async def test_a_failure_while_following_a_started_run_keeps_its_id(self, mocker: MockerFixture, follow_error: Exception) -> None:
        """A paid run that is still going is not reported as a plain network failure: the error names it."""
        client = _mocked_client(mocker)
        client.wait_for_result.side_effect = follow_error

        with pytest.raises(HostedRunPollingError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(mthds_files=[BUNDLE_FILE]))

        error = exc_info.value
        assert error.pipeline_run_id == RUN_ID
        assert error.__cause__ is follow_error
        assert RUN_ID in error.message
        assert error.user_action is not None
        assert RUN_ID in error.user_action.detail

    @pytest.mark.asyncio
    async def test_a_results_body_that_does_not_parse_keeps_the_run_id(self, mocker: MockerFixture) -> None:
        """A drift in the results body fails after the run completed: the run id still locates it."""
        with pytest.raises(ValidationError) as drift:
            RunResults.model_validate({"main_stuff": 1})
        client = _mocked_client(mocker)
        client.wait_for_result.side_effect = drift.value

        with pytest.raises(HostedRunPollingError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(mthds_files=[BUNDLE_FILE]))

        assert exc_info.value.pipeline_run_id == RUN_ID

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "terminal_error",
        [
            RunFailedError("Run finished with status FAILED: boom", run_id=RUN_ID, status=RunStatus.FAILED),
            RunTimeoutError(f"Run '{RUN_ID}' did not finish within 1200s", run_id=RUN_ID, timeout_seconds=1200.0),
            MissingMainStuffError(f"Completed run '{RUN_ID}' returned no main stuff", run_id=RUN_ID),
        ],
    )
    async def test_an_error_that_names_the_run_already_is_raised_as_it_is(self, mocker: MockerFixture, terminal_error: Exception) -> None:
        client = _mocked_client(mocker)
        client.wait_for_result.side_effect = terminal_error

        with pytest.raises(type(terminal_error)) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(mthds_files=[BUNDLE_FILE]))

        assert exc_info.value is terminal_error

    @pytest.mark.asyncio
    async def test_a_bare_runner_runs_the_blocking_route(self, mocker: MockerFixture) -> None:
        """A runner whose handshake names no run store is never started: it gets the blocking execute, as the SDK does."""
        bare_version = '{"protocol_version":"0.1.0","implementation":"pipelex-api","implementation_version":"0.76.0"}'
        client = _mocked_client(mocker, version=bare_version)
        lift = mocker.patch(f"{HOSTED_RUN_MODULE}.results_from_execute", return_value=DONE)

        outcome = await run_hosted(client=client, request=HostedRunRequest(method_ref=DOCUMENT_METHOD_REF, pipe_code="extract"))

        client.start.assert_not_awaited()
        client.execute.assert_awaited_once_with(
            pipe_code="extract",
            mthds_contents=None,
            inputs=None,
            dynamic_output_concept_ref=None,
            method_ref=DOCUMENT_METHOD_REF,
            method_id=None,
        )
        lift.assert_called_once_with(client.execute.return_value)
        assert outcome.results is DONE

    @pytest.mark.asyncio
    async def test_a_server_without_the_run_store_falls_back_to_the_blocking_route(self, mocker: MockerFixture) -> None:
        """A start refused for a missing run store created no run, so the blocking execute cannot run it twice."""
        client = _mocked_client(mocker)
        client.start.side_effect = RunLifecycleUnavailableError("no run store", api_url="https://hosted.test")
        mocker.patch(f"{HOSTED_RUN_MODULE}.results_from_execute", return_value=DONE)

        outcome = await run_hosted(client=client, request=HostedRunRequest(mthds_files=[BUNDLE_FILE]))

        client.execute.assert_awaited_once()
        client.wait_for_result.assert_not_awaited()
        assert outcome.results is DONE

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("transport_error", "expected_code"),
        [
            (httpx.ConnectError("connection refused"), "ConnectError"),
            (httpx.ReadTimeout("timed out"), "ABORT_TIMEOUT"),
        ],
    )
    async def test_a_transport_failure_on_any_route_is_an_unreachable_api(
        self, mocker: MockerFixture, transport_error: httpx.TransportError, expected_code: str
    ) -> None:
        """The SDK lets httpx's error through on the routes it inherits from mthds; the run maps it as the SDK's own routes do."""
        client = _mocked_client(mocker)
        client.start.side_effect = transport_error

        with pytest.raises(ApiUnreachableError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(mthds_files=[BUNDLE_FILE]))

        assert exc_info.value.api_url == "https://hosted.test"
        assert exc_info.value.code == expected_code
        assert str(exc_info.value).startswith("Could not reach Pipelex API at https://hosted.test")

    @pytest.mark.parametrize(
        "source",
        [
            {},
            {"method_ref": DOCUMENT_METHOD_REF, "method_id": "mt_abc123"},
            {"mthds_files": [BUNDLE_FILE], "method_ref": DOCUMENT_METHOD_REF},
            {"mthds_files": []},
        ],
    )
    def test_a_request_names_exactly_one_source(self, source: dict[str, Any]) -> None:
        """A bundle, a published address or a stored method: one of the three, never none or several."""
        with pytest.raises(ValidationError, match="exactly one"):
            HostedRunRequest.model_validate(source)
