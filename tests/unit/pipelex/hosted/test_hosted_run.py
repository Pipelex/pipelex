from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mthds.protocol.input_form import PipeInputFormDescriptor
from mthds.protocol.models import VersionInfo
from mthds.protocol.problem.registry import RetryVerdict
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.crate_models import CrateInvalidReport, PipeIORequest, PipeIOValidReport
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    MethodFileTransferError,
    MethodFileTransferOperation,
    MethodFileTransferReason,
    MissingMainStuffError,
    RunFailedError,
    RunLifecycleUnavailableError,
    RunTimeoutError,
)
from pipelex_sdk.runs import PipelexRunResultStart, RunResults, RunStatus
from pipelex_sdk.upload import UploadRecord
from pydantic import ValidationError

from pipelex.errors.problem import ProblemView
from pipelex.hosted.exceptions import (
    HostedLocalFileUploadUnavailableError,
    HostedMethodInvalidError,
    HostedRunOutcomeUnknownError,
    HostedRunPollingError,
)
from pipelex.hosted.hosted_run import HostedRunRequest, run_hosted
from tests.unit.pipelex.hosted.test_data import HostedDescriptors, HostedPipeIoRefusals, HostedPipeIoVerdicts, HostedVersions

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

#: A local method's tree, as the CLI reads it: each bundle's bytes by tree path, which the SDK sends as `files`.
BUNDLE_CONTENTS = {"probe.mthds": b'domain = "probe"\n'}
#: What the transport says of a connection reset on the request it fails.
CONNECTION_RESET = "connection reset"
#: A tree past the SDK's inline threshold of 256 KiB, which travels by the hash of each file once the missing blobs are uploaded.
LARGE_BUNDLE_CONTENTS = {"probe.mthds": b'domain = "probe"\n' + b"#" * (300 * 1024) + b"\n"}
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


def _invalid_report(*, verdict_json: str) -> CrateInvalidReport:
    return CrateInvalidReport.model_validate_json(verdict_json)


def _pipe_io_refusal(*, problem_json: str) -> ApiResponseError:
    """The error the client raises when `POST /v1/pipe-io` answers this problem document, which it reads as the problem."""
    problem: dict[str, Any] = json.loads(problem_json)
    return ApiResponseError(
        f"API POST /v1/pipe-io failed (422): {problem['detail']}",
        api_url="https://hosted.test",
        status=422,
        status_text="Unprocessable Entity",
        response_body=problem_json,
        headers={"content-type": "application/problem+json"},
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


def _connect_error_from(*, cause: BaseException) -> httpx.ConnectError:
    """A `ConnectError` raised from `cause`, as httpx raises one for a connection dropped during the TLS handshake."""
    error = httpx.ConnectError("connection failed")
    error.__cause__ = cause
    return error


async def _sdk_transport_failure(*, transport_error: httpx.TransportError) -> ApiUnreachableError:
    """The error the real client raises when its transport fails this way while sending `POST /v1/start`."""

    def _fail(_request: httpx.Request) -> httpx.Response:
        raise transport_error

    sdk_client = PipelexAPIClient(api_key="plx_sk_test_not_a_secret", base_url="https://hosted.test")
    sdk_client.client = httpx.AsyncClient(transport=httpx.MockTransport(_fail))
    try:
        with pytest.raises(ApiUnreachableError) as exc_info:
            await sdk_client.start(pipe_code="entry", contents=BUNDLE_CONTENTS)
    finally:
        await sdk_client.close()
    assert exc_info.value.__cause__ is transport_error
    return exc_info.value


def _client_reset_on(*, path: str, requested: list[str]) -> PipelexAPIClient:
    """The real client over a deployment with a blob store whose connection is reset once `path` was requested.

    Every request is recorded in `requested`; the version handshake is answered, and any other request is unexpected.
    """
    reset = httpx.ReadError(CONNECTION_RESET)

    def _handle(request: httpx.Request) -> httpx.Response:
        requested.append(f"{request.method} {request.url.path}")
        if request.url.path == path:
            raise reset
        if request.url.path == "/v1/version":
            return httpx.Response(200, content=HostedVersions.HOSTED_WITH_BLOB_STORE.encode("utf-8"), headers={"content-type": "application/json"})
        pytest.fail(f"unexpected request {request.method} {request.url.path}")

    sdk_client = PipelexAPIClient(api_key="plx_sk_test_not_a_secret", base_url="https://hosted.test")
    sdk_client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))
    return sdk_client


class TestHostedRun:
    @pytest.mark.asyncio
    async def test_a_local_method_without_inputs_starts_and_waits_on_its_tree(self, mocker: MockerFixture) -> None:
        """A local method travels as its tree, handed to the SDK as its contents, and with no inputs nothing is asked of pipe-io."""
        client = _mocked_client(mocker)
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, pipe_code="entry", dynamic_output_concept_ref="probe.Thing")

        outcome = await run_hosted(client=client, request=request)

        client.start.assert_awaited_once_with(
            pipe_code="entry",
            contents=BUNDLE_CONTENTS,
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
            contents=None,
            inputs=None,
            dynamic_output_concept_ref=None,
            method_ref=expected_method_ref,
            method_id=expected_method_id,
        )

    @pytest.mark.asyncio
    async def test_inputs_naming_no_local_file_go_straight_to_the_run(self, mocker: MockerFixture) -> None:
        """Inputs naming no file on this machine need no preparation, so the signature is not even read."""
        client = _mocked_client(mocker)
        inputs = {"text": "report.pdf is a word here, not a file", "page": "https://example.com/page.png", "nested": {"cover": None}}
        request = HostedRunRequest(method_ref="github.com/Pipelex/methods/text_stats@v0.1.7", inputs=inputs)

        outcome = await run_hosted(client=client, request=request)

        client.pipe_io.assert_not_awaited()
        client.upload_file.assert_not_awaited()
        assert client.start.await_args.kwargs["inputs"] == inputs
        assert outcome.pipe_ref is None

    @pytest.mark.asyncio
    async def test_an_address_dependency_runs_with_inputs_naming_no_local_file(self, mocker: MockerFixture) -> None:
        """pipe-io loads no package nothing shipped; with no file to upload it is not asked, and the run route fetches the dependency."""
        client = _mocked_client(mocker, pipe_io_report=_invalid_report(verdict_json=HostedPipeIoVerdicts.UNSHIPPED_ADDRESS_DEPENDENCY))
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, inputs={"item": "a widget"})

        outcome = await run_hosted(client=client, request=request)

        client.pipe_io.assert_not_awaited()
        assert client.start.await_args.kwargs["inputs"] == {"item": "a widget"}
        assert outcome.results is DONE

    @pytest.mark.asyncio
    async def test_a_local_file_is_anchored_then_uploaded_before_the_run(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A relative file path resolves against the inputs file's directory, is uploaded, and the run gets the storage URI.

        The signature is read once: the upload is driven from that one answer, not from a second pipe-io request. pipe-io
        and the run receive the same tree.
        """
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "invoice.pdf").write_bytes(b"%PDF")
        report = _valid_report(pipe_ref=HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF, descriptor_json=HostedDescriptors.MIXED_FILE_POSITIONS)
        client = _mocked_client(mocker, pipe_io_report=report)
        upload = UploadRecord(uri="pipelex-storage://uploads/abc.pdf", filename="invoice.pdf", content_type="application/pdf", size=4)
        client.upload_file.return_value = upload
        request = HostedRunRequest(
            contents=BUNDLE_CONTENTS,
            pipe_code="summarize_report",
            inputs={"document": "docs/invoice.pdf", "notes": "see attached"},
            inputs_base_dir=tmp_path,
        )

        outcome = await run_hosted(client=client, request=request)

        sent_contents: dict[str, bytes | str] = dict(BUNDLE_CONTENTS)
        client.pipe_io.assert_awaited_once_with(PipeIORequest(contents=sent_contents, pipe_ref="summarize_report"))
        assert client.start.await_args.kwargs["contents"] == BUNDLE_CONTENTS
        client.prepare_inputs.assert_not_awaited()
        client.upload_file.assert_awaited_once_with(str(tmp_path / "docs" / "invoice.pdf"))
        assert client.start.await_args.kwargs["inputs"] == {"document": {"url": "pipelex-storage://uploads/abc.pdf"}, "notes": "see attached"}
        assert outcome.uploads == [upload]
        assert outcome.pipe_ref == HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF

    @pytest.mark.asyncio
    async def test_a_null_optional_file_beside_a_local_file_reaches_the_run_as_null(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A local run takes an explicit null for an optional image; the upload walk leaves it for the run to read."""
        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
        report = _valid_report(pipe_ref=HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF, descriptor_json=HostedDescriptors.MIXED_FILE_POSITIONS)
        client = _mocked_client(mocker, pipe_io_report=report)
        client.upload_file.return_value = UploadRecord(
            uri="pipelex-storage://uploads/invoice.pdf", filename="invoice.pdf", content_type="application/pdf", size=4
        )
        inputs: dict[str, Any] = {
            "document": {"url": "invoice.pdf", "mime_type": "application/pdf"},
            "report": {"title": "Report", "cover": None},
            "pages": ["invoice.pdf", None],
        }
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, inputs=inputs, inputs_base_dir=tmp_path)

        await run_hosted(client=client, request=request)

        client.upload_file.assert_awaited_once_with(str(tmp_path / "invoice.pdf"))
        assert client.start.await_args.kwargs["inputs"] == {
            "document": {"url": "pipelex-storage://uploads/invoice.pdf", "mime_type": "application/pdf"},
            "report": {"title": "Report", "cover": None},
            "pages": [{"url": "pipelex-storage://uploads/invoice.pdf"}, None],
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "verdict_json",
        [
            HostedPipeIoVerdicts.UNSHIPPED_ADDRESS_DEPENDENCY,
            HostedPipeIoVerdicts.UNSHIPPED_ADDRESS_DEPENDENCY_AFTER_AN_UNREADABLE_ITEM,
        ],
        ids=["problem_items", "after_an_unreadable_item"],
    )
    async def test_a_local_file_for_a_method_whose_address_dependency_was_not_shipped_is_refused_naming_it(
        self, mocker: MockerFixture, tmp_path: Path, verdict_json: str
    ) -> None:
        """pipe-io loads only the packages shipped with the method, and answers a call into another one with its verdict.

        The run route fetches that dependency, so the method is not at fault: the error names the dependency, read from
        the parameters of the verdict's `method.dependency_missing` item, an item before it that does not read skipped,
        and the URL to use, never the verdict's advice to fix the method.
        """
        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
        client = _mocked_client(mocker, pipe_io_report=_invalid_report(verdict_json=verdict_json))
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, inputs={"document": "invoice.pdf"}, inputs_base_dir=tmp_path)

        with pytest.raises(HostedLocalFileUploadUnavailableError) as exc_info:
            await run_hosted(client=client, request=request)

        error = exc_info.value
        assert "address-based dependencies" in error.message
        assert "github.com/mthds/scoring-lib/scoring" in error.message
        assert error.user_action is not None
        assert "https URL" in error.user_action.detail
        assert "Fix the method" not in error.user_action.detail
        client.upload_file.assert_not_awaited()
        client.start.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "verdict_json",
        [HostedPipeIoVerdicts.ADDRESS_DEPENDENCY_WORDS_ONLY, HostedPipeIoVerdicts.DEPENDENCY_CYCLE],
        ids=["words_only", "dependency_cycle"],
    )
    async def test_a_verdict_naming_no_unshipped_dependency_is_the_method_s_fault(
        self, mocker: MockerFixture, tmp_path: Path, verdict_json: str
    ) -> None:
        """The refusal is read from an item's code and parameters, never its words: an item only quoting them is the
        method's, and so is a `method.dependency_missing` item whose reason is not `not_found`, such as a cycle.
        """
        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
        client = _mocked_client(mocker, pipe_io_report=_invalid_report(verdict_json=verdict_json))
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, inputs={"document": "invoice.pdf"}, inputs_base_dir=tmp_path)

        with pytest.raises(HostedMethodInvalidError):
            await run_hosted(client=client, request=request)

        client.upload_file.assert_not_awaited()
        client.start.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_pipe_io_refusal_is_the_hosted_api_s_refusal(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A request pipe-io refuses, here for a form it does not accept, is the hosted API's refusal, propagated as it is."""
        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
        refusal = _pipe_io_refusal(problem_json=HostedPipeIoRefusals.UNSUPPORTED_FORM)
        client = _mocked_client(mocker)
        client.pipe_io.side_effect = refusal
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, inputs={"document": "invoice.pdf"}, inputs_base_dir=tmp_path)

        with pytest.raises(ApiResponseError) as exc_info:
            await run_hosted(client=client, request=request)

        assert exc_info.value is refusal
        client.start.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_method_that_does_not_load_is_refused_before_the_run_with_its_items(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """pipe-io's verdict lists its faults as problem items, each naming its file by its tree path, before any run starts."""
        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
        invalid = _invalid_report(verdict_json=HostedPipeIoVerdicts.UNKNOWN_MODEL)
        client = _mocked_client(mocker, pipe_io_report=invalid)
        request = HostedRunRequest(contents=BUNDLE_CONTENTS, inputs={"document": "invoice.pdf"}, inputs_base_dir=tmp_path)

        with pytest.raises(HostedMethodInvalidError) as exc_info:
            await run_hosted(client=client, request=request)

        assert exc_info.value.errors == invalid.errors
        assert [item.code for item in exc_info.value.errors] == ["model.unknown"]
        assert exc_info.value.errors[0].location is not None
        assert exc_info.value.errors[0].location.file == "lib/b.mthds"
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == "method.invalid"
        assert problem.errors == invalid.errors
        assert "Bundle does not load" in exc_info.value.message
        client.upload_file.assert_not_awaited()
        client.start.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "follow_error",
        [
            ApiUnreachableError(
                "Could not reach Pipelex API at https://hosted.test (ConnectError)", api_url="https://hosted.test", network_code="ConnectError"
            ),
            httpx.RemoteProtocolError("server disconnected"),
            json.JSONDecodeError("Expecting value", "<html>Bad gateway</html>", 0),
        ],
    )
    async def test_a_failure_while_following_a_started_run_keeps_its_id(self, mocker: MockerFixture, follow_error: Exception) -> None:
        """A paid run that is still going is not reported as a plain network failure: the error names it."""
        client = _mocked_client(mocker)
        client.wait_for_result.side_effect = follow_error

        with pytest.raises(HostedRunPollingError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

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
            await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

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
            await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

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
            contents=None,
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

        outcome = await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

        client.execute.assert_awaited_once()
        client.wait_for_result.assert_not_awaited()
        assert outcome.results is DONE

    @pytest.mark.asyncio
    async def test_an_acknowledged_start_is_announced_before_the_run_is_followed(self, mocker: MockerFixture) -> None:
        """The caller learns the run's id as soon as the hosted API acknowledges it, so an interrupted wait can still name it."""
        client = _mocked_client(mocker)
        announced: list[str] = []

        def _on_started(*, pipeline_run_id: str) -> None:
            announced.append(pipeline_run_id)

        def _follow(run_id: str) -> RunResults:
            assert announced == [run_id], "the start must be announced before the run is followed"
            return DONE

        client.wait_for_result.side_effect = _follow

        await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS), on_started=_on_started)

        assert announced == [RUN_ID]

    @pytest.mark.asyncio
    async def test_a_blocking_run_announces_no_start(self, mocker: MockerFixture) -> None:
        bare_version = '{"protocol_version":"0.1.0","implementation":"pipelex-api","implementation_version":"0.76.0"}'
        client = _mocked_client(mocker, version=bare_version)
        mocker.patch(f"{HOSTED_RUN_MODULE}.results_from_execute", return_value=DONE)
        on_started = mocker.Mock()

        await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS), on_started=on_started)

        on_started.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("transport_error", "expected_code"),
        [
            (httpx.ConnectError("connection refused"), "ConnectError"),
            (httpx.ConnectTimeout("connect timed out"), "ConnectTimeout"),
            (httpx.PoolTimeout("no free connection"), "PoolTimeout"),
            (httpx.UnsupportedProtocol("unknown scheme"), "UnsupportedProtocol"),
        ],
    )
    async def test_a_transport_failure_before_the_start_is_sent_is_an_unreachable_api(
        self, mocker: MockerFixture, transport_error: httpx.TransportError, expected_code: str
    ) -> None:
        """No byte of the start left this machine, as the SDK reads the failure, so no run exists: checking the network is the right advice."""
        sdk_error = await _sdk_transport_failure(transport_error=transport_error)
        # `client.unreachable` or `client.timeout`, both of which a retry may pass: no run may exist.
        assert sdk_error.problem.effective_retry == RetryVerdict.YES
        client = _mocked_client(mocker)
        client.start.side_effect = sdk_error

        with pytest.raises(ApiUnreachableError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

        assert exc_info.value is sdk_error
        assert exc_info.value.api_url == "https://hosted.test"
        assert exc_info.value.network_code == expected_code
        assert str(exc_info.value).startswith("Could not reach Pipelex API at https://hosted.test")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "transport_error",
        [
            httpx.ReadError("connection reset"),
            httpx.RemoteProtocolError("Server disconnected without sending a response."),
            httpx.ReadTimeout("timed out"),
            httpx.WriteError("broken pipe"),
            httpx.WriteTimeout("write timed out"),
            httpx.ProxyError("proxy refused"),
            _connect_error_from(cause=ConnectionResetError("reset during the TLS handshake")),
        ],
        ids=["read", "remote_protocol", "read_timeout", "write", "write_timeout", "proxy", "handshake_reset"],
    )
    @pytest.mark.parametrize("bare_runner", [False, True])
    async def test_a_transport_failure_after_the_run_request_was_sent_is_an_unknown_outcome(
        self, mocker: MockerFixture, transport_error: httpx.TransportError, bare_runner: bool
    ) -> None:
        """The hosted API may have created the run before the connection failed, as the SDK reads the failure, so "check the
        network" would lead to a second paid run. A proxy's failure and a handshake reset are among them: neither proves the
        request never left.
        """
        sdk_error = await _sdk_transport_failure(transport_error=transport_error)
        assert sdk_error.problem.code == "client.outcome_unknown"
        assert sdk_error.problem.effective_retry == RetryVerdict.OUTCOME_UNKNOWN
        bare_version = '{"protocol_version":"0.1.0","implementation":"pipelex-api","implementation_version":"0.76.0"}'
        client = _mocked_client(mocker, version=bare_version) if bare_runner else _mocked_client(mocker)
        client.start.side_effect = sdk_error
        client.execute.side_effect = sdk_error

        with pytest.raises(HostedRunOutcomeUnknownError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

        error = exc_info.value
        assert error.__cause__ is sdk_error
        assert type(transport_error).__name__ in error.message
        assert error.user_action is not None
        assert "run history" in error.user_action.detail
        assert "before running again" in error.user_action.detail

    @pytest.mark.asyncio
    async def test_a_tree_upload_that_fails_is_the_sdk_s_transfer_error_and_no_unknown_outcome(self, mocker: MockerFixture) -> None:
        """The SDK uploads a large tree before the run request leaves, and says no run started: that is not an unknown outcome."""
        transfer_error = MethodFileTransferError(
            "Uploading the file with SHA-256 abc to storage failed (503 Service Unavailable), so the run was not started.",
            operation=MethodFileTransferOperation.UPLOAD,
            reason=MethodFileTransferReason.STORAGE_ERROR,
            sha256="abc",
            status=503,
        )
        client = _mocked_client(mocker)
        client.start.side_effect = transfer_error

        with pytest.raises(MethodFileTransferError) as exc_info:
            await run_hosted(client=client, request=HostedRunRequest(contents=BUNDLE_CONTENTS))

        assert exc_info.value is transfer_error
        client.wait_for_result.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_connection_reset_on_the_start_request_itself_is_an_unknown_outcome(self) -> None:
        """A tree inline asks nothing before the start, so the reset is on the request that may have created the run."""
        requested: list[str] = []
        sdk_client = _client_reset_on(path="/v1/start", requested=requested)

        try:
            with pytest.raises(HostedRunOutcomeUnknownError) as exc_info:
                await run_hosted(client=sdk_client, request=HostedRunRequest(contents=BUNDLE_CONTENTS, pipe_code="entry"))
        finally:
            await sdk_client.close()

        assert requested == ["GET /v1/version", "POST /v1/start"]
        cause = exc_info.value.__cause__
        assert isinstance(cause, ApiUnreachableError)
        assert cause.problem.code == "client.outcome_unknown"
        assert f"ReadError: {CONNECTION_RESET}" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_a_connection_reset_on_the_blob_request_of_a_large_tree_is_an_unreachable_api(self) -> None:
        """The SDK asks which blobs the hosted API lacks before the start leaves, so a reset there started no run: it stays
        the SDK's error, and no start is sent.
        """
        requested: list[str] = []
        sdk_client = _client_reset_on(path="/v1/blobs/missing", requested=requested)

        try:
            with pytest.raises(ApiUnreachableError) as exc_info:
                await run_hosted(client=sdk_client, request=HostedRunRequest(contents=LARGE_BUNDLE_CONTENTS, pipe_code="entry"))
        finally:
            await sdk_client.close()

        assert "POST /v1/blobs/missing" in requested
        assert "POST /v1/start" not in requested
        assert exc_info.value.problem.code == "client.unreachable"
        assert isinstance(exc_info.value.__cause__, httpx.ReadError)

    @pytest.mark.parametrize(
        "source",
        [
            {},
            {"method_ref": DOCUMENT_METHOD_REF, "method_id": "mt_abc123"},
            {"contents": BUNDLE_CONTENTS, "method_ref": DOCUMENT_METHOD_REF},
            {"contents": {}},
        ],
    )
    def test_a_request_names_exactly_one_source(self, source: dict[str, Any]) -> None:
        """A bundle, a published address or a stored method: one of the three, never none or several."""
        with pytest.raises(ValidationError, match="exactly one"):
            HostedRunRequest.model_validate(source)
