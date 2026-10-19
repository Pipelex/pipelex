from typing import Any, cast

import pytest
from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.answers import read_answer
from mthds.protocol.problem.client_problems import make_client_problem
from mthds.protocol.problem.registry import CoreCode
from mthds.runners.api.exceptions import ApiResponseError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.usage_stats_reporting import (
    CodeGenerationReport,
    MethodValidationReport,
    RunUsageFacts,
    build_run_usage_events,
    reported_model,
    shipped_backend_models,
    usage_stats_codegen_target,
)
from pipelex.system.usage_stats.usage_stats_contract import (
    UsageStatsCodegenArtifact,
    UsageStatsCodegenTarget,
    UsageStatsErrorDomain,
    UsageStatsEventName,
    UsageStatsOutcome,
    UsageStatsProvider,
)
from pipelex.system.usage_stats.usage_stats_events import UsageStatsEvent
from pipelex.system.usage_stats.usage_stats_runs import RunInferenceTally, sent_usage_stats_error, usage_stats_error, usage_stats_failure_domain
from pipelex.tracing.trace_events import TraceEvent
from tests.helpers.recovered_problem import make_recovered_url_refusal
from tests.helpers.usage_stats_run_events import envelope_of, llm_usage_event, pipe_start_event
from tests.helpers.usage_stats_schema import assert_envelope_is_valid

_SHIPPED_ANTHROPIC_MODEL = "claude-4-sonnet"
_SECRET_MESSAGE = "secret failure text"


def _facts(
    *,
    mocker: MockerFixture,
    outcome: UsageStatsOutcome = UsageStatsOutcome.SUCCEEDED,
    error: BaseException | None = None,
    events: list[TraceEvent] | None = None,
    tally: RunInferenceTally | None = None,
) -> RunUsageFacts:
    main_pipe = mocker.MagicMock()
    main_pipe.is_controller = False
    return RunUsageFacts(
        outcome=outcome,
        error=error,
        is_dry_run=False,
        duration_seconds=1.5,
        main_pipe=main_pipe,
        own_pipes=[],
        own_concepts=[],
        has_image_input=True,
        has_document_input=False,
        events=events,
        closed_graph=None,
        tally=tally,
    )


def _properties(*, usage_event: UsageStatsEvent) -> dict[str, Any]:
    envelope = envelope_of(event=usage_event)
    assert_envelope_is_valid(envelope)
    return cast("dict[str, Any]", envelope["properties"])


def _recorded_events(mocker: MockerFixture) -> list[UsageStatsEvent]:
    mocker.patch("pipelex.pipeline.usage_stats_reporting.usage_stats_are_enabled", return_value=True)
    concept_library = mocker.MagicMock()
    concept_library.list_own_concepts.return_value = []
    mocker.patch("pipelex.pipeline.usage_stats_reporting.get_concept_library", return_value=concept_library)
    recorded: list[UsageStatsEvent] = []

    def _record(*, event: UsageStatsEvent) -> None:
        recorded.append(event)

    mocker.patch("pipelex.pipeline.usage_stats_reporting.record_usage_stats_event", side_effect=_record)
    return recorded


def _validate_raising(*, error: BaseException) -> None:
    with MethodValidationReport():
        raise error


def _validate_declared_valid_then_exit() -> None:
    """A valid library refused for its pending signatures: the verdict stays valid."""
    with MethodValidationReport() as report:
        report.declare_valid()
        raise SystemExit(1)


def _validate_rendering_the_verdict_then_exit() -> None:
    with MethodValidationReport():
        try:
            raise ValidateBundleError(message=_SECRET_MESSAGE)
        except ValidateBundleError:
            raise SystemExit(1) from None


def _generate_raising(*, error: BaseException) -> None:
    with CodeGenerationReport(artifact=UsageStatsCodegenArtifact.TYPES):
        raise error


def _answered_refusal(*, status: int, body: str) -> ApiResponseError:
    """A refusal a server answered with `body`, with the problem the MTHDS client reads from it, inferred from the status if the body names none."""
    reading = read_answer(status=status, body=body, headers={}, creates_run=False)
    return ApiResponseError(
        f"API POST /v1/start failed ({status})",
        problem=reading.problem,
        api_url="https://runner.test",
        status=status,
        status_text="",
        response_body=body,
    )


class TestUsageStatsReporting:
    def test_run_with_usage_reports_one_model_used_per_model(self, mocker: MockerFixture) -> None:
        """Pipe counts and tokens come from the run's events, failures and backends from its tally, one `model_used` per model."""
        tally = RunInferenceTally()
        for _ in range(2):
            tally.note_call(
                model_handle=_SHIPPED_ANTHROPIC_MODEL,
                backend_name="anthropic",
                failure_domain=None,
                images_generated=0,
                pages_extracted=0,
            )
        tally.note_call(
            model_handle=_SHIPPED_ANTHROPIC_MODEL,
            backend_name="anthropic",
            failure_domain=UsageStatsErrorDomain.RUNTIME,
            images_generated=0,
            pages_extracted=0,
        )
        events: list[TraceEvent] = [
            pipe_start_event(pipe_type="PipeSequence", sequence=0),
            pipe_start_event(pipe_type="PipeLLM", sequence=1),
            pipe_start_event(pipe_type="PipeLLM", sequence=2),
            pipe_start_event(pipe_type="PipeFromAPlugin", sequence=3),
            llm_usage_event(
                model_name=_SHIPPED_ANTHROPIC_MODEL, backend_name="anthropic", input_tokens=100, output_tokens=50, cached_tokens=20, sequence=4
            ),
            llm_usage_event(model_name=_SHIPPED_ANTHROPIC_MODEL, backend_name="anthropic", input_tokens=200, output_tokens=10, sequence=5),
        ]
        run_event, model_event = build_run_usage_events(facts=_facts(mocker=mocker, events=events, tally=tally))
        run = _properties(usage_event=run_event)
        assert run_event.name == UsageStatsEventName.RUN_COMPLETED
        assert run["outcome"] == "succeeded"
        assert run["usage_known"] is True
        assert run["feature_image_input"] is True
        assert run["duration_ms"] == 1500
        assert (run["pipes_sequence"], run["pipes_llm"], run["pipes_other"], run["pipes_extract"]) == (1, 2, 1, 0)
        assert (run["models_used"], run["inference_calls"], run["inference_failures"]) == (1, 3, 1)
        assert (run["input_tokens"], run["output_tokens"], run["cached_tokens"]) == (300, 60, 20)
        assert run["cost_usd"] > 0
        model = _properties(usage_event=model_event)
        assert (model["provider"], model["model"], model["calls"], model["failures"], model["failures_runtime"]) == (
            "anthropic",
            _SHIPPED_ANTHROPIC_MODEL,
            3,
            1,
            1,
        )
        assert (model["failures_input"], model["failures_method"], model["failures_account"], model["failures_operator"]) == (0, 0, 0, 0)
        assert (model["input_tokens"], model["output_tokens"], model["cached_tokens"]) == (300, 60, 20)
        assert model["cost_usd"] == run["cost_usd"]

    def test_a_call_that_fell_back_is_attributed_to_the_backend_that_made_it(self, mocker: MockerFixture) -> None:
        """One handle served by two backends in one run, which call the model by the same id: each backend's calls,
        failures and tokens are its own, by the backend each usage report names.
        """
        tally = RunInferenceTally()
        for backend_name, failed in (("anthropic", True), ("bedrock", False), ("anthropic", False)):
            tally.note_call(
                model_handle=_SHIPPED_ANTHROPIC_MODEL,
                backend_name=backend_name,
                failure_domain=UsageStatsErrorDomain.RUNTIME if failed else None,
                images_generated=0,
                pages_extracted=0,
            )
        events: list[TraceEvent] = [
            llm_usage_event(
                model_name=_SHIPPED_ANTHROPIC_MODEL, backend_name="bedrock", input_tokens=40, output_tokens=20, model_id="claude-sonnet-4", sequence=0
            ),
            llm_usage_event(
                model_name=_SHIPPED_ANTHROPIC_MODEL,
                backend_name="anthropic",
                input_tokens=100,
                output_tokens=50,
                model_id="claude-sonnet-4",
                sequence=1,
            ),
        ]
        _, *model_events = build_run_usage_events(facts=_facts(mocker=mocker, events=events, tally=tally))
        by_provider = {properties["provider"]: properties for properties in (_properties(usage_event=event) for event in model_events)}
        assert set(by_provider) == {"anthropic", "bedrock"}
        assert (by_provider["anthropic"]["calls"], by_provider["anthropic"]["failures"], by_provider["anthropic"]["input_tokens"]) == (2, 1, 100)
        assert (by_provider["bedrock"]["calls"], by_provider["bedrock"]["failures"], by_provider["bedrock"]["input_tokens"]) == (1, 0, 40)

    def test_unrated_model_leaves_the_run_cost_out(self, mocker: MockerFixture) -> None:
        """A model on a backend of the user's own is `custom` and `other`, and its missing rates leave the run's cost out."""
        tally = RunInferenceTally()
        tally.note_call(
            model_handle=_SHIPPED_ANTHROPIC_MODEL,
            backend_name="anthropic",
            failure_domain=None,
            images_generated=0,
            pages_extracted=0,
        )
        tally.note_call(
            model_handle="my-own-gpu-model",
            backend_name="my_gpu_box",
            failure_domain=None,
            images_generated=0,
            pages_extracted=0,
        )
        events: list[TraceEvent] = [
            llm_usage_event(model_name=_SHIPPED_ANTHROPIC_MODEL, backend_name="anthropic", input_tokens=10, output_tokens=5, sequence=0),
            llm_usage_event(model_name="my-own-gpu-model", backend_name="my_gpu_box", input_tokens=10, output_tokens=5, is_rated=False, sequence=1),
        ]
        run_event, *model_events = build_run_usage_events(facts=_facts(mocker=mocker, events=events, tally=tally))
        run = _properties(usage_event=run_event)
        assert "cost_usd" not in run
        assert run["models_used"] == 2
        models = {_properties(usage_event=event)["model"]: _properties(usage_event=event) for event in model_events}
        assert set(models) == {_SHIPPED_ANTHROPIC_MODEL, "other"}
        assert models["other"]["provider"] == "custom"
        assert "cost_usd" not in models["other"]

    def test_usage_unknown_sends_no_counts_and_no_model_used(self, mocker: MockerFixture) -> None:
        """With tracing or usage events off, the run says its usage is unknown and nothing else."""
        usage_events = build_run_usage_events(facts=_facts(mocker=mocker, events=None, tally=RunInferenceTally()))
        assert len(usage_events) == 1
        run = _properties(usage_event=usage_events[0])
        assert run["usage_known"] is False
        assert not [name for name in run if name.startswith("pipes_") or name.endswith("_tokens") or name == "cost_usd"]

    @pytest.mark.parametrize(
        ("outcome", "error"),
        [
            (UsageStatsOutcome.FAILED, PipelexError(_SECRET_MESSAGE)),
            (UsageStatsOutcome.FAILED, RuntimeError(_SECRET_MESSAGE)),
            (UsageStatsOutcome.CANCELLED, None),
        ],
    )
    def test_failed_and_cancelled_runs(self, mocker: MockerFixture, outcome: UsageStatsOutcome, error: BaseException | None) -> None:
        events: list[TraceEvent] = [llm_usage_event(model_name=_SHIPPED_ANTHROPIC_MODEL, backend_name="anthropic", input_tokens=7, output_tokens=3)]
        run_event = build_run_usage_events(facts=_facts(mocker=mocker, outcome=outcome, error=error, events=events))[0]
        envelope = envelope_of(event=run_event)
        assert_envelope_is_valid(envelope)
        run = envelope["properties"]
        assert run["outcome"] == outcome
        assert run["input_tokens"] == 7
        if outcome.is_failed:
            assert (run["error_code"], run["error_domain"]) == ("runtime.unexpected", "runtime")
        else:
            assert "error_code" not in run
            assert "error_domain" not in run
        assert "secret" not in str(envelope)

    def test_a_recovered_problem_is_counted_by_its_own_code(self) -> None:
        """A failure reporting a problem recovered from a worker is counted by that problem's code and domain, not by its carrier's class."""
        assert usage_stats_error(error=make_recovered_url_refusal()) == ("input.url_unreachable", UsageStatsErrorDomain.INPUT)

    def test_a_request_error_is_counted_by_the_problem_it_carries(self) -> None:
        """An MTHDS client's request error is no Pipelex error, and carries its problem: it is counted by that, not as the catch-all."""
        unreachable = PipelineRequestError(
            "the runner could not be reached",
            problem=make_client_problem(CoreCode.CLIENT_UNREACHABLE, params={"base_url": "https://runner.test"}),
        )

        assert usage_stats_error(error=unreachable) == ("client.unreachable", UsageStatsErrorDomain.RUNTIME)

    @pytest.mark.parametrize(
        ("body", "expected", "expected_sent"),
        [
            # A gateway's page: the client infers `runtime.unavailable` from the 503, which no statistic reports.
            ("<html>502 Bad Gateway</html>", ("runtime.unexpected", UsageStatsErrorDomain.RUNTIME), None),
            # A problem document naming its code and its domain is counted by them, on every path.
            (
                '{"detail": "The input is invalid", "code": "input.invalid", "domain": "input"}',
                ("input.invalid", UsageStatsErrorDomain.INPUT),
                ("input.invalid", UsageStatsErrorDomain.INPUT),
            ),
        ],
    )
    def test_an_answered_refusal_is_counted_by_what_its_body_sent_alone(
        self, body: str, expected: tuple[str, UsageStatsErrorDomain], expected_sent: tuple[str, UsageStatsErrorDomain] | None
    ) -> None:
        """One rule for a refusal a server answered: its body's code and domain, never the problem the client inferred from the status."""
        refusal = _answered_refusal(status=503, body=body)

        assert usage_stats_error(error=refusal) == expected
        assert sent_usage_stats_error(error=refusal) == expected_sent
        assert usage_stats_failure_domain(error=refusal) == expected[1]

    @pytest.mark.parametrize(
        "error",
        [
            make_recovered_url_refusal(),
            PipelexError("a fault of ours"),
            PipelineRequestError("refused", problem=make_client_problem(CoreCode.CLIENT_NOT_CONFIGURED, params={"setting": "base_url"})),
            RuntimeError("no Pipelex error at all"),
        ],
    )
    def test_a_failed_call_s_domain_is_read_off_its_code_alone(self, mocker: MockerFixture, error: Exception) -> None:
        """The cheap reading a failed inference call takes agrees with the problem's, and builds no problem to get it."""
        expected_domain = usage_stats_error(error=error).domain
        to_problem_spy = mocker.patch.object(PipelexError, "to_problem")

        assert usage_stats_failure_domain(error=error) == expected_domain
        to_problem_spy.assert_not_called()

    def test_a_failed_run_carries_its_error_s_code_and_domain(self, mocker: MockerFixture) -> None:
        """A failed run's `run_completed` names its error's code and that code's domain, which the gate accepts."""
        run_event = build_run_usage_events(facts=_facts(mocker=mocker, outcome=UsageStatsOutcome.FAILED, error=make_recovered_url_refusal()))[0]
        run = _properties(usage_event=run_event)
        assert (run["error_code"], run["error_domain"]) == ("input.url_unreachable", "input")

    @pytest.mark.parametrize(
        ("backend_name", "model_handle", "provider", "model"),
        [
            ("anthropic", _SHIPPED_ANTHROPIC_MODEL, "anthropic", _SHIPPED_ANTHROPIC_MODEL),
            ("openai", _SHIPPED_ANTHROPIC_MODEL, "openai", "other"),
            ("anthropic", "my-fine-tune-secret", "anthropic", "other"),
            ("pipelex_manifold", _SHIPPED_ANTHROPIC_MODEL, "pipelex_manifold", _SHIPPED_ANTHROPIC_MODEL),
            ("pipelex_manifold", "my-fine-tune-secret", "pipelex_manifold", "other"),
            ("my_company_gateway", _SHIPPED_ANTHROPIC_MODEL, "custom", "other"),
            (None, _SHIPPED_ANTHROPIC_MODEL, "custom", "other"),
            ("anthropic", "has spaces in it", "anthropic", "other"),
        ],
    )
    def test_provider_and_model_are_from_closed_lists(self, backend_name: str | None, model_handle: str, provider: str, model: str) -> None:
        """A model is named only when a backend table this release ships names it; Manifold serves every table."""
        assert _SHIPPED_ANTHROPIC_MODEL in shipped_backend_models()["anthropic"]
        reported_provider = UsageStatsProvider.for_backend(backend_name=backend_name)
        assert reported_provider == provider
        assert reported_model(provider=reported_provider, model_handle=model_handle) == model
        assert UsageStatsProvider(provider) == reported_provider

    def test_method_validated(self, mocker: MockerFixture) -> None:
        """Valid, invalid with its error count, and failed when no verdict was reached."""
        recorded = _recorded_events(mocker)
        with MethodValidationReport() as valid_report:
            valid_report.describe(pipes=[])
            valid_report.count_warnings(count=2)
        with pytest.raises(ValidateBundleError):
            _validate_raising(error=ValidateBundleError(message=_SECRET_MESSAGE))
        with pytest.raises(OSError, match=_SECRET_MESSAGE):
            _validate_raising(error=OSError(_SECRET_MESSAGE))
        with pytest.raises(SystemExit):
            _validate_declared_valid_then_exit()
        outcomes = [(_properties(usage_event=event)["outcome"], _properties(usage_event=event)["errors"]) for event in recorded]
        assert outcomes == [("valid", 0), ("invalid", 1), ("failed", 0), ("valid", 0)]
        assert _properties(usage_event=recorded[0])["warnings"] == 2

    def test_a_validation_statistic_never_changes_the_validation(self, mocker: MockerFixture) -> None:
        """A library that cannot be described, or a bundle whose event cannot be built, loses the event and nothing else."""
        recorded = _recorded_events(mocker)
        mocker.patch("pipelex.pipeline.usage_stats_reporting.get_concept_library", side_effect=RuntimeError("no library loaded"))
        steps: list[str] = []
        with MethodValidationReport() as report:
            report.describe(pipes=[])
            steps.append("validated")
        assert steps == ["validated"]
        mocker.patch("pipelex.pipeline.usage_stats_reporting.bundle_shape_of", side_effect=ValueError("an event that will not validate"))
        with pytest.raises(ValidateBundleError):
            _validate_raising(error=ValidateBundleError(message=_SECRET_MESSAGE))
        assert recorded == []

    def test_invalid_verdict_handled_on_the_way_out_is_read(self, mocker: MockerFixture) -> None:
        """A CLI renders the invalid verdict and exits: the verdict is found on the exception it handled."""
        recorded = _recorded_events(mocker)
        with pytest.raises(SystemExit):
            _validate_rendering_the_verdict_then_exit()
        assert _properties(usage_event=recorded[0])["outcome"] == "invalid"

    def test_code_generated(self, mocker: MockerFixture) -> None:
        recorded = _recorded_events(mocker)
        crate = mocker.MagicMock()
        crate.pipes = [object(), object()]
        crate.concepts = [object()]
        with CodeGenerationReport(artifact=UsageStatsCodegenArtifact.TYPES, target=usage_stats_codegen_target(target="ts-zod")) as types_report:
            types_report.describe(crate=crate)
        with pytest.raises(OSError, match=_SECRET_MESSAGE):
            _generate_raising(error=OSError(_SECRET_MESSAGE))
        with CodeGenerationReport(artifact=UsageStatsCodegenArtifact.INPUTS) as inputs_report:
            inputs_report.declare_failed()
        with CodeGenerationReport(artifact=UsageStatsCodegenArtifact.STRUCTURES):
            pass
        generated = [_properties(usage_event=event) for event in recorded]
        assert [(event["artifact"], event.get("target"), event["outcome"]) for event in generated] == [
            ("types", "ts-zod", "succeeded"),
            ("types", "other", "failed"),
            ("inputs", None, "failed"),
            ("structures", None, "succeeded"),
        ]
        assert (generated[0]["bundle_pipes"], generated[0]["bundle_concepts"]) == (2, 1)
        assert usage_stats_codegen_target(target="kotlin") == UsageStatsCodegenTarget.OTHER

    def test_nothing_is_built_while_statistics_are_off(self, mocker: MockerFixture) -> None:
        record = mocker.patch("pipelex.pipeline.usage_stats_reporting.record_usage_stats_event")
        mocker.patch("pipelex.pipeline.usage_stats_reporting.usage_stats_are_enabled", return_value=False)
        with MethodValidationReport(), CodeGenerationReport(artifact=UsageStatsCodegenArtifact.TYPES):
            pass
        record.assert_not_called()
