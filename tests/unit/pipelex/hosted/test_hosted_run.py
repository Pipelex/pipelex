from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mthds.protocol.input_form import PipeInputFormDescriptor
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.crate_models import CrateInvalidReport, MthdsFileItem, PipeIORequest, PipeIOValidReport
from pipelex_sdk.errors import ApiUnreachableError
from pipelex_sdk.prepare_inputs import PreparedInputs
from pipelex_sdk.runs import RunResults
from pipelex_sdk.upload import UploadRecord
from pydantic import ValidationError

from pipelex.hosted.hosted_run import HostedRunRequest, run_hosted
from tests.unit.pipelex.hosted.test_data import HostedDescriptors

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

BUNDLE_FILE = MthdsFileItem(content='domain = "probe"\n', source="probe.mthds")
DOCUMENT_METHOD_REF = "github.com/Pipelex/methods/documents@v0.1.7"


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


def _mocked_client(mocker: MockerFixture, *, pipe_io_report: PipeIOValidReport | CrateInvalidReport | None = None) -> MagicMock:
    client: MagicMock = mocker.create_autospec(PipelexAPIClient, instance=True)
    client.start_and_wait.return_value = RunResults(pipeline_run_id="run_1", main_stuff={"text": "done"})
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

        client.start_and_wait.assert_awaited_once_with(
            pipe_code="entry",
            mthds_contents=[BUNDLE_FILE.content],
            inputs=None,
            dynamic_output_concept_ref="probe.Thing",
            method_ref=None,
            method_id=None,
        )
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

        client.start_and_wait.assert_awaited_once_with(
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
        assert client.start_and_wait.await_args.kwargs["inputs"] == inputs
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
        assert client.start_and_wait.await_args.kwargs["inputs"] == prepared_inputs
        assert outcome.uploads == [upload]
        assert outcome.pipe_ref == HostedDescriptors.MIXED_FILE_POSITIONS_PIPE_REF

    @pytest.mark.asyncio
    async def test_a_method_that_does_not_load_runs_unprepared_so_the_run_says_why(self, mocker: MockerFixture) -> None:
        """Preparation has no signature to walk; the run route refuses the method with its own located diagnostics."""
        invalid = CrateInvalidReport(is_valid=False, validation_errors=[], message="Bundle does not load")
        client = _mocked_client(mocker, pipe_io_report=invalid)
        inputs = {"document": "invoice.pdf"}
        request = HostedRunRequest(mthds_files=[BUNDLE_FILE], inputs=inputs)

        outcome = await run_hosted(client=client, request=request)

        client.prepare_inputs.assert_not_awaited()
        assert client.start_and_wait.await_args.kwargs["inputs"] == inputs
        assert outcome.pipe_ref is None

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
        client.base_url = "https://hosted.test"
        client.start_and_wait.side_effect = transport_error

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
