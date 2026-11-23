import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.providers.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.providers.portkey.portkey_factory import PortkeyFactory
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata, UnitJobId
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


def _run_metadata(*, capture_pipe_codes: bool | None) -> RunMetadata:
    return RunMetadata(
        user_id="user-42",
        pipeline_run_id="run-1",
        storage_scope="tenant/run-1",
        read_scope=None,
        capture_pipe_codes=capture_pipe_codes,
    )


def _make_llm_job(*, capture_pipe_codes: bool | None) -> LLMJob:
    job_metadata = JobMetadata(
        run_metadata=_run_metadata(capture_pipe_codes=capture_pipe_codes),
        pipe_code="extract_invoice",
        unit_job_id=UnitJobId.LLM_GEN_OBJECT,
        otel_context=OtelContext(
            trace_id=1234,
            trace_name="extract_invoice_abc",
            trace_name_redacted="abc",
            span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
            is_sampled=True,
        ),
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(user_text="hello"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _portkey_span_name(*, mocker: MockerFixture, deployment_captures: bool, capture_pipe_codes: bool | None) -> str:
    telemetry_manager = mocker.MagicMock()
    telemetry_manager.is_custom_portkey_tracing_enabled.return_value = True
    mocker.patch("pipelex.providers.portkey.portkey_factory.get_telemetry_manager", return_value=telemetry_manager)
    mocker.patch.object(TelemetryManagerAbstract, "is_capture_pipe_codes_enabled", return_value=deployment_captures)
    mocker.patch.object(TelemetryManagerAbstract, "is_capture_output_class_name_enabled", return_value=deployment_captures)
    inference_model = mocker.MagicMock()
    inference_model.extra_headers = None
    inference_model.max_tokens = None
    extra_headers, _ = PortkeyFactory.make_extras(
        inference_model=inference_model,
        inference_job=_make_llm_job(capture_pipe_codes=capture_pipe_codes),
        output_desc="Invoice",
    )
    return extra_headers[PortkeyHeaderKey.SPAN_NAME]


class TestCapturePipeCodesForRun:
    @pytest.mark.parametrize(
        ("deployment_captures", "capture_pipe_codes", "expected"),
        [
            (False, None, False),
            (True, None, True),
            (False, True, True),
            (True, False, False),
        ],
    )
    def test_the_runs_setting_wins_and_the_deployments_stands_without_one(
        self, mocker: MockerFixture, deployment_captures: bool, capture_pipe_codes: bool | None, expected: bool
    ) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "is_capture_pipe_codes_enabled", return_value=deployment_captures)
        mocker.patch.object(TelemetryManagerAbstract, "is_capture_output_class_name_enabled", return_value=deployment_captures)
        run_metadata = _run_metadata(capture_pipe_codes=capture_pipe_codes)

        assert TelemetryManagerAbstract.is_capture_pipe_codes_enabled_for_run(run_metadata=run_metadata) is expected
        assert TelemetryManagerAbstract.is_capture_output_class_name_enabled_for_run(run_metadata=run_metadata) is expected

    @pytest.mark.parametrize(
        ("deployment_captures", "capture_pipe_codes", "expected_span_name"),
        [
            (False, None, f"{OTelConstants.PIPE_CODE_REDACTED}: llm_gen_object -> {OTelConstants.OUTPUT_CLASS_REDACTED}"),
            (False, True, "extract_invoice: llm_gen_object -> Invoice"),
            (True, False, f"{OTelConstants.PIPE_CODE_REDACTED}: llm_gen_object -> {OTelConstants.OUTPUT_CLASS_REDACTED}"),
            (True, None, "extract_invoice: llm_gen_object -> Invoice"),
        ],
    )
    def test_portkeys_span_name_shows_what_the_run_allows(
        self, mocker: MockerFixture, deployment_captures: bool, capture_pipe_codes: bool | None, expected_span_name: str
    ) -> None:
        span_name = _portkey_span_name(mocker=mocker, deployment_captures=deployment_captures, capture_pipe_codes=capture_pipe_codes)

        assert span_name == expected_span_name
