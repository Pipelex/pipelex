# The self-hosted telemetry check: the stock `telemetry.toml` still feeds PostHog, OTLP and Langfuse.
#
# A self-hoster gets `telemetry.toml` from the kit, as `pipelex init telemetry` writes it, and turns its destinations on with
# the keys the file and the documentation name, in a `telemetry_override.toml` beside it. This check does exactly
# that: it copies the kit's file into `~/.pipelex/`, writes the override, loads both through the real
# loader, boots the real telemetry manager for the `cli` integration mode, which the stock file allows, and runs a
# method live, its model calls answered by a stand-in worker. Every privacy default of the stock file stays as
# shipped (no content, no pipe codes, no output class names on the PostHog stream).
#
# It then reads what each destination received: the run's events and spans on the PostHog client, and the same
# spans on the `[[otlp]]` exporter and on Langfuse's, which are OTLP exporters too. The PostHog client and the two
# OTLP exporters are stand-ins, so nothing leaves the process.


from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import posthog
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from typing_extensions import override

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_runtime_hub
from pipelex.system.job_metadata import UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.singleton import MetaSingleton
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome
from pipelex.system.telemetry.otel_constants import (
    GenAISpanAttr,
    InferenceKind,
    OTelConstants,
    PipelexSpanAttr,
    PostHogAttr,
    PostHogEvent,
    SpanCategory,
)
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TELEMETRY_CONFIG_OVERRIDE_FILE_NAME, PostHogMode, TelemetryConfig
from pipelex.system.telemetry.telemetry_factory import TelemetryFactory
from pipelex.system.telemetry.telemetry_loader import load_telemetry_config
from pipelex.system.telemetry.telemetry_manager import TelemetryManager
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs
    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

pytestmark = pytest.mark.usefixtures("no_pipelex_home")

SELF_HOSTER_ID = "self-hoster"
POSTHOG_ENDPOINT = "https://posthog.self-hosted.test"
OTLP_ENDPOINT = "https://collector.self-hosted.test/v1/traces"
LANGFUSE_ENDPOINT = "https://langfuse.self-hosted.test"
LANGFUSE_TRACES_ENDPOINT = f"{LANGFUSE_ENDPOINT}/api/public/otel/v1/traces"

# What the self-hoster's override turns on, with the keys the stock file and the docs name. The PostHog key and
# endpoint stay the stock file's placeholders, read from the environment as they would be.
POSTHOG_ON = f"""
[custom_posthog]
mode = "identified"
user_id = "{SELF_HOSTER_ID}"

[custom_posthog.tracing]
enabled = true
"""
SPAN_DESTINATIONS_ON = f"""
[langfuse]
enabled = true
endpoint = "{LANGFUSE_ENDPOINT}"
public_key = "${{LANGFUSE_PUBLIC_KEY}}"
secret_key = "${{LANGFUSE_SECRET_KEY}}"

[[otlp]]
name = "collector"
endpoint = "{OTLP_ENDPOINT}"
"""

PIPE_CODE = "describe_company"
METHOD = f"""
domain = "self_hosted_telemetry_check"
description = "Describe a company, the one model call the check traces"
main_pipe = "{PIPE_CODE}"

[pipe.{PIPE_CODE}]
type = "PipeLLM"
description = "Describe the company the brief is about"
inputs = {{ brief = "Text" }}
output = "Text"
model = "$testing-text"
prompt = "Describe the company this brief is about: $brief"
"""
BRIEF = "Acme builds reusable rockets in Toulouse."
COMPLETION = "Acme builds reusable rockets for research labs."
INPUTS: PipelineInputs = {"brief": BRIEF}

STAND_IN_BACKEND = "stand_in"
STAND_IN_MODEL_ID = "stand-in-model-2026"
INPUT_TOKENS = 1000
OUTPUT_TOKENS = 200
# $1 and $4 a million tokens: 1,000 in and 200 out cost $0.001 and $0.0008.
RATES = {CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 4.0}
INPUT_COST_USD = 0.001
OUTPUT_COST_USD = 0.0008
TOTAL_COST_USD = 0.0018


class StandInLLMWorker(LLMWorkerAbstract):
    """Answers a generation without a provider, recording the usage a provider would have answered with, or fails as told."""

    def __init__(self, *, inference_model: InferenceModelSpec, error: Exception | None) -> None:
        super().__init__(inference_model=inference_model, reporting_delegate=None)
        self._error = error

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        tokens_usage = llm_job.job_report.llm_tokens_usage
        assert tokens_usage is not None
        tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: INPUT_TOKENS, TokenCategory.OUTPUT: OUTPUT_TOKENS}
        if self._error is not None:
            raise self._error
        return COMPLETION

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        raise NotImplementedError


def _stand_in_worker_factory(*, error: Exception | None) -> Any:
    def _stand_in_worker(*, llm_handle: str) -> StandInLLMWorker:
        inference_model = InferenceModelSpec(
            backend_name=STAND_IN_BACKEND,
            name=llm_handle,
            sdk="stand_in",
            model_type=ModelType.LLM,
            model_id=STAND_IN_MODEL_ID,
            inputs=["text"],
            outputs=["text", "structured"],
            costs=RATES,
            thinking_mode=ThinkingMode.NONE,
            max_tokens=None,
            max_prompt_images=None,
        )
        return StandInLLMWorker(inference_model=inference_model, error=error)

    return _stand_in_worker


class Destinations:
    """What each destination received: the PostHog client's captures, and the spans of the OTLP and Langfuse exporters."""

    def __init__(self, *, posthog_class: Any, otlp: InMemorySpanExporter, langfuse: InMemorySpanExporter) -> None:
        self.posthog_class = posthog_class
        self.otlp = otlp
        self.langfuse = langfuse

    def posthog_captures(self) -> list[dict[str, Any]]:
        """Every capture on the operator's client, as its keyword arguments, the event name under `event` whichever way it was passed."""
        captures: list[dict[str, Any]] = []
        for call in self.posthog_class.return_value.capture.call_args_list:
            capture = dict(call.kwargs)
            if call.args:
                capture["event"] = call.args[0]
            captures.append(capture)
        return captures

    def posthog_events(self, event: str) -> list[dict[str, Any]]:
        return [capture for capture in self.posthog_captures() if capture["event"] == event]


def _load_stock_telemetry_config(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override_toml: str) -> TelemetryConfig:
    """The kit's `telemetry.toml`, as `pipelex init telemetry` writes it into `~/.pipelex/`, with the self-hoster's override beside it."""
    fake_home = tmp_path / "home"
    global_config_dir = fake_home / ".pipelex"
    global_config_dir.mkdir(parents=True)
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    shutil.copyfile(Path(str(get_kit_configs_dir() / TELEMETRY_CONFIG_FILE_NAME)), global_config_dir / TELEMETRY_CONFIG_FILE_NAME)
    (global_config_dir / TELEMETRY_CONFIG_OVERRIDE_FILE_NAME).write_text(override_toml, encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "home", lambda: fake_home)
        patch.setattr(Path, "cwd", lambda: project_root)
        return load_telemetry_config(secrets_provider=EnvSecretsProvider())


def _boot_self_hosted_telemetry(*, mocker: MockerFixture, telemetry_config: TelemetryConfig) -> tuple[TelemetryManagerAbstract, Destinations]:
    """The real telemetry manager for the `cli` integration mode, installed for the run, with stand-ins at every network edge."""
    # The singleton registry and the hub's manager are restored when the test ends, so the session's stay as they were.
    mocker.patch.dict(MetaSingleton.instances)
    TelemetryManagerAbstract.clear_instance()
    posthog_class = mocker.patch("pipelex.system.telemetry.telemetry_manager.Posthog")
    mocker.patch("posthog.default_client", None)
    mocker.patch("posthog.privacy_mode", False)
    otlp = InMemorySpanExporter()
    langfuse = InMemorySpanExporter()
    exporters_by_endpoint = {OTLP_ENDPOINT: otlp, LANGFUSE_TRACES_ENDPOINT: langfuse}

    def _span_exporter(*, endpoint: str, **_exporter_options: Any) -> InMemorySpanExporter:
        return exporters_by_endpoint[endpoint]

    mocker.patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", side_effect=_span_exporter)

    telemetry_manager = TelemetryFactory.make_telemetry_manager(
        secrets_provider=EnvSecretsProvider(),
        integration_mode=IntegrationMode.CLI,
        telemetry_config=telemetry_config,
    )
    mocker.patch.object(get_runtime_hub(), "_telemetry_manager", telemetry_manager)
    return telemetry_manager, Destinations(posthog_class=posthog_class, otlp=otlp, langfuse=langfuse)


def _generation_span(spans: tuple[ReadableSpan, ...]) -> ReadableSpan:
    (generation,) = [span for span in spans if (span.attributes or {}).get(PipelexSpanAttr.SPAN_CATEGORY) == SpanCategory.INFERENCE]
    return generation


def _assert_full_spans(spans: tuple[ReadableSpan, ...], *, is_error: bool) -> None:
    """An OTLP backend, Langfuse included, receives the run's pipe span and its generation span, with every new attribute and full values."""
    (pipe_span,) = [span for span in spans if (span.attributes or {}).get(PipelexSpanAttr.SPAN_CATEGORY) != SpanCategory.INFERENCE]
    assert (pipe_span.attributes or {}).get(PipelexSpanAttr.PIPE_CODE) == PIPE_CODE
    generation = _generation_span(spans)
    attributes = dict(generation.attributes or {})
    assert generation.parent is not None
    assert pipe_span.context is not None
    assert generation.parent.span_id == pipe_span.context.span_id
    assert attributes[GenAISpanAttr.OPERATION_NAME] == "chat"
    assert attributes[GenAISpanAttr.PROVIDER_NAME] == attributes[PipelexSpanAttr.INFERENCE_BACKEND] == STAND_IN_BACKEND
    assert attributes[GenAISpanAttr.REQUEST_MODEL] == attributes[GenAISpanAttr.RESPONSE_MODEL] == STAND_IN_MODEL_ID
    assert attributes[PipelexSpanAttr.MODEL_HANDLE]
    assert attributes[PipelexSpanAttr.INFERENCE_KIND] == InferenceKind.LLM
    assert attributes[PipelexSpanAttr.ATTEMPT_COUNT] == 1
    assert attributes[PipelexSpanAttr.PIPE_CODE] == PIPE_CODE
    assert attributes[PipelexSpanAttr.UNIT_JOB_ID] == UnitJobId.LLM_GEN_TEXT
    assert (attributes[GenAISpanAttr.USAGE_INPUT_TOKENS], attributes[GenAISpanAttr.USAGE_OUTPUT_TOKENS]) == (INPUT_TOKENS, OUTPUT_TOKENS)
    assert math.isclose(cast("float", attributes[PipelexSpanAttr.INPUT_COST_USD]), INPUT_COST_USD)
    assert math.isclose(cast("float", attributes[PipelexSpanAttr.OUTPUT_COST_USD]), OUTPUT_COST_USD)
    assert math.isclose(cast("float", attributes[PipelexSpanAttr.TOTAL_COST_USD]), TOTAL_COST_USD)
    assert generation.resource.attributes["service.version"] == get_package_version()
    if is_error:
        assert generation.status.status_code == StatusCode.ERROR
        assert attributes[GenAISpanAttr.ERROR_TYPE] == InferenceErrorCategory.TRANSIENT
    else:
        assert generation.status.status_code != StatusCode.ERROR
        assert GenAISpanAttr.ERROR_TYPE not in attributes


def _assert_posthog_generation(destinations: Destinations, *, is_error: bool) -> None:
    (generation,) = destinations.posthog_events(PostHogEvent.GENERATION)
    properties = generation["properties"]
    assert generation["distinct_id"] == SELF_HOSTER_ID
    assert properties[PostHogAttr.PROVIDER] == STAND_IN_BACKEND
    assert properties[PostHogAttr.MODEL] == STAND_IN_MODEL_ID
    assert properties[PostHogAttr.MODEL_HANDLE]
    assert properties[PostHogAttr.INFERENCE_KIND] == InferenceKind.LLM
    assert properties[PostHogAttr.INFERENCE_BACKEND] == STAND_IN_BACKEND
    assert properties[PostHogAttr.ATTEMPT_COUNT] == 1
    (execute,) = destinations.posthog_events(EventName.PIPELINE_EXECUTE)
    assert properties[PostHogAttr.PIPELINE_RUN_ID] == execute["properties"][EventProperty.PIPELINE_RUN_ID]
    assert properties[PostHogAttr.PIPELEX_VERSION] == get_package_version()
    assert (properties[PostHogAttr.INPUT_TOKENS], properties[PostHogAttr.OUTPUT_TOKENS]) == (INPUT_TOKENS, OUTPUT_TOKENS)
    assert math.isclose(properties[PostHogAttr.INPUT_COST_USD], INPUT_COST_USD)
    assert math.isclose(properties[PostHogAttr.OUTPUT_COST_USD], OUTPUT_COST_USD)
    assert math.isclose(properties[PostHogAttr.TOTAL_COST_USD], TOTAL_COST_USD)
    assert properties[PostHogAttr.IS_ERROR] is is_error
    assert properties[PostHogAttr.ERROR] == (InferenceErrorCategory.TRANSIENT if is_error else None)
    # The stock privacy defaults hold: no pipe code and no content, neither the prompt nor the completion, reach the PostHog stream.
    assert PIPE_CODE not in str(properties)
    assert BRIEF not in str(properties)
    assert COMPLETION not in str(properties)


def _assert_posthog_run_events(destinations: Destinations, *, outcome: Outcome) -> None:
    """The run's trace start and its two events reach the operator's PostHog, on the configured user, with the runtime's version."""
    (execute,) = destinations.posthog_events(EventName.PIPELINE_EXECUTE)
    (complete,) = destinations.posthog_events(EventName.PIPELINE_COMPLETE)
    assert complete["properties"][EventProperty.PIPELINE_OUTCOME] == outcome
    run_id = execute["properties"][EventProperty.PIPELINE_RUN_ID]
    assert complete["properties"][EventProperty.PIPELINE_RUN_ID] == run_id
    # The trace start is the `$ai_span` whose span id is the one derived from its trace, sent before any pipe span.
    (trace_start,) = [
        span
        for span in destinations.posthog_events(PostHogEvent.SPAN)
        if span["properties"][PostHogAttr.SPAN_ID]
        == TelemetryManager.make_trace_start_span_id(trace_id=int(span["properties"][PostHogAttr.TRACE_ID], 16))
    ]
    assert trace_start["properties"][EventProperty.PIPELINE_RUN_ID] == run_id
    # The pipe's own span follows, in the same trace, its pipe code redacted by the stock defaults.
    trace_start_span_id = trace_start["properties"][PostHogAttr.SPAN_ID]
    (pipe_span,) = [span for span in destinations.posthog_events(PostHogEvent.SPAN) if span["properties"][PostHogAttr.SPAN_ID] != trace_start_span_id]
    assert pipe_span["properties"][PostHogAttr.TRACE_ID] == trace_start["properties"][PostHogAttr.TRACE_ID]
    assert PIPE_CODE not in str(pipe_span["properties"])
    for event in (execute, complete, trace_start, pipe_span):
        assert event["distinct_id"] == SELF_HOSTER_ID
        assert event["properties"][PostHogAttr.PIPELEX_VERSION] == get_package_version()


@pytest.mark.asyncio(loop_scope="class")
class TestSelfHostedTelemetryCheck:
    @pytest.fixture(autouse=True)
    def _self_hoster_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The environment the stock file's placeholders read, and none of the switches that would turn telemetry off or join a host trace.

        `DO_NOT_TRACK` is cleared for the manager this check boots, whose every network edge is a stand-in.
        """
        monkeypatch.delenv(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY, raising=False)
        monkeypatch.delenv(OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY, raising=False)
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_self_hosted_check")
        monkeypatch.setenv("POSTHOG_ENDPOINT", POSTHOG_ENDPOINT)
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-self-hosted-check")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-self-hosted-check")

    async def test_the_stock_file_feeds_posthog_otlp_and_langfuse_with_the_new_attributes(
        self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        telemetry_config = _load_stock_telemetry_config(tmp_path=tmp_path, monkeypatch=monkeypatch, override_toml=POSTHOG_ON + SPAN_DESTINATIONS_ON)
        # The stock file's privacy defaults are what the check runs with.
        assert telemetry_config.custom_posthog.tracing.capture.content is False
        assert telemetry_config.custom_posthog.tracing.capture.pipe_codes is False
        telemetry_manager, destinations = _boot_self_hosted_telemetry(mocker=mocker, telemetry_config=telemetry_config)
        assert isinstance(telemetry_manager, TelemetryManager)
        posthog_client_kwargs = destinations.posthog_class.call_args.kwargs
        assert posthog_client_kwargs["project_api_key"] == "phc_self_hosted_check"
        assert posthog_client_kwargs["host"] == POSTHOG_ENDPOINT
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", side_effect=_stand_in_worker_factory(error=None))

        await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(pipe_code=PIPE_CODE, mthds_contents=[METHOD], inputs=INPUTS)
        telemetry_manager.teardown()

        _assert_posthog_run_events(destinations, outcome=Outcome.SUCCESS)
        _assert_posthog_generation(destinations, is_error=False)
        _assert_full_spans(destinations.otlp.get_finished_spans(), is_error=False)
        _assert_full_spans(destinations.langfuse.get_finished_spans(), is_error=False)

    async def test_a_failed_call_reaches_every_destination_as_an_error_with_its_category(
        self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        telemetry_config = _load_stock_telemetry_config(tmp_path=tmp_path, monkeypatch=monkeypatch, override_toml=POSTHOG_ON + SPAN_DESTINATIONS_ON)
        telemetry_manager, destinations = _boot_self_hosted_telemetry(mocker=mocker, telemetry_config=telemetry_config)
        error = LLMCompletionError(message="the provider refused", error_category=InferenceErrorCategory.TRANSIENT)
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", side_effect=_stand_in_worker_factory(error=error))

        with pytest.raises(PipelineExecutionError):
            await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(pipe_code=PIPE_CODE, mthds_contents=[METHOD], inputs=INPUTS)
        telemetry_manager.teardown()

        _assert_posthog_run_events(destinations, outcome=Outcome.FAILURE)
        _assert_posthog_generation(destinations, is_error=True)
        _assert_full_spans(destinations.otlp.get_finished_spans(), is_error=True)
        _assert_full_spans(destinations.langfuse.get_finished_spans(), is_error=True)

    async def test_the_stock_file_with_posthog_left_off_still_feeds_otlp_and_langfuse(
        self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        telemetry_config = _load_stock_telemetry_config(tmp_path=tmp_path, monkeypatch=monkeypatch, override_toml=SPAN_DESTINATIONS_ON)
        assert telemetry_config.custom_posthog.mode == PostHogMode.OFF
        telemetry_manager, destinations = _boot_self_hosted_telemetry(mocker=mocker, telemetry_config=telemetry_config)
        assert isinstance(telemetry_manager, TelemetryManager)
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", side_effect=_stand_in_worker_factory(error=None))

        await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(pipe_code=PIPE_CODE, mthds_contents=[METHOD], inputs=INPUTS)
        telemetry_manager.teardown()

        destinations.posthog_class.assert_not_called()
        assert posthog.default_client is None
        _assert_full_spans(destinations.otlp.get_finished_spans(), is_error=False)
        _assert_full_spans(destinations.langfuse.get_finished_spans(), is_error=False)
