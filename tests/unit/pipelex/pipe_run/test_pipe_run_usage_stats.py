import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex.base_exceptions import PipelexError
from pipelex.pipe_run import pipe_run as pipe_run_module
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.tracing_assembly import RunTraceEvents
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.runtime import IntegrationMode
from pipelex.system.trace_context import TraceContext
from pipelex.system.usage_stats.usage_stats_client import configure_usage_stats_for_runtime
from pipelex.system.usage_stats.usage_stats_runs import current_run_tally, usage_stats_error_domain
from tests.helpers.usage_stats_process import make_project_dir, usage_stats_switched_on
from tests.helpers.usage_stats_run_events import USAGE_STATS_RUN_ID, llm_usage_event
from tests.helpers.usage_stats_schema import assert_envelope_is_valid

if TYPE_CHECKING:
    from pipelex.tracing.trace_events import TraceEvent

_MODEL = "claude-4-sonnet"
_FAILURE = PipelexError("secret failure after the first call")


def _job(*, mocker: MockerFixture, is_traced: bool) -> Any:
    job = mocker.MagicMock()
    trace_context = TraceContext(
        graph_id=USAGE_STATS_RUN_ID,
        data_inclusion=DataInclusionConfig(pipe_and_concept_registry=False, stuff_json_content=False, error_stack_traces=False),
        emit_graph_events=False,
        emit_usage_events=True,
        run_mode=PipeRunMode.LIVE,
    )
    job.job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", pipeline_run_id=USAGE_STATS_RUN_ID, storage_scope="test/scope", read_scope=None),
        trace_context=trace_context if is_traced else None,
    )
    job.pipe_run_params.run_mode = PipeRunMode.LIVE
    job.working_memory = None
    job.pipe.is_controller = False
    job.pipe.code = "secret_main_pipe"
    return job


def _note_one_call() -> None:
    tally = current_run_tally()
    assert tally is not None
    tally.note_call(model_handle=_MODEL, backend_name="anthropic", failed=False, failure_category=None, images_generated=0, pages_extracted=0)


def _call_then_fail(pipe_job: Any) -> Any:
    del pipe_job
    _note_one_call()
    raise _FAILURE


class _RunOutput:
    graph_spec = None

    def set_job_metadata(self, *, job_metadata: JobMetadata) -> None:
        del job_metadata


def _call_then_succeed(pipe_job: Any) -> Any:
    del pipe_job
    _note_one_call()
    return _RunOutput()


def _succeed_untallied(pipe_job: Any) -> Any:
    del pipe_job
    assert current_run_tally() is None
    return _RunOutput()


def _cancelled(pipe_job: Any) -> Any:
    del pipe_job
    _note_one_call()
    raise asyncio.CancelledError


def _debug_events(stderr: str) -> list[dict[str, Any]]:
    return [json.loads(line)["usage_stats_debug"] for line in stderr.splitlines() if line.startswith('{"usage_stats_debug"')]


@pytest.fixture
def run_seams(mocker: MockerFixture) -> MockType:
    """The run's surroundings, which a unit test does not boot: no graph tracer, an empty library, the run's usage events.

    Returns the stand-in for reading the run's trace events.
    """
    events: list[TraceEvent] = [llm_usage_event(model_name=_MODEL, backend_name="anthropic", input_tokens=120, output_tokens=30)]
    mocker.patch.object(pipe_run_module.GraphTracerManager, "get_instance", return_value=None)
    read_events = mocker.patch.object(pipe_run_module, "read_run_trace_events", return_value=RunTraceEvents(events=events, read_error=None))
    mocker.patch.object(pipe_run_module, "assemble_tracing_on_output")
    mocker.patch.object(pipe_run_module, "get_own_pipes", return_value=[])
    concept_library = mocker.MagicMock()
    concept_library.list_own_concepts.return_value = []
    mocker.patch.object(pipe_run_module, "get_concept_library", return_value=concept_library)
    return read_events


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRunUsageStats:
    @pytest.mark.parametrize(
        ("router_run", "outcome", "raised"),
        [
            (_call_then_fail, "failed", PipelexError),
            (_cancelled, "cancelled", asyncio.CancelledError),
            (_call_then_succeed, "succeeded", None),
        ],
    )
    @pytest.mark.usefixtures("run_seams")
    async def test_every_run_end_reports_with_its_tokens(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        router_run: Any,
        outcome: str,
        raised: type[BaseException] | None,
    ) -> None:
        """A run that raises after its first inference call still sends its `run_completed`, with the tokens it used."""
        router = mocker.AsyncMock()
        router.run = mocker.AsyncMock(side_effect=router_run)
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTHON)
            pipe_run = PipeRun(pipe_router=router)
            if raised is None:
                await pipe_run.run(pipe_job=_job(mocker=mocker, is_traced=True))
            else:
                with pytest.raises(raised):
                    await pipe_run.run(pipe_job=_job(mocker=mocker, is_traced=True))
            stderr = capsys.readouterr().err
        run_event, model_event = _debug_events(stderr)
        for envelope in (run_event, model_event):
            assert_envelope_is_valid(envelope)
        assert "secret" not in stderr
        run = run_event["properties"]
        assert run_event["event"] == "run_completed"
        assert run["outcome"] == outcome
        assert run["usage_known"] is True
        assert (run["inference_calls"], run["input_tokens"], run["output_tokens"], run["models_used"]) == (1, 120, 30, 1)
        assert run["surface"] == "python"
        if outcome == "failed":
            assert run["error_domain"] == usage_stats_error_domain(error=_FAILURE)
        assert model_event["event"] == "model_used"
        assert (model_event["properties"]["provider"], model_event["properties"]["model"]) == ("anthropic", _MODEL)

    async def test_untraced_run_reports_usage_unknown(
        self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], run_seams: MockType
    ) -> None:
        """Statistics never turn tracing on: an untraced run says its usage is unknown and sends no `model_used`."""
        router = mocker.AsyncMock()
        router.run = mocker.AsyncMock(side_effect=_call_then_fail)
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTHON)
            with pytest.raises(PipelexError):
                await PipeRun(pipe_router=router).run(pipe_job=_job(mocker=mocker, is_traced=False))
            events = _debug_events(capsys.readouterr().err)
        assert [event["event"] for event in events] == ["run_completed"]
        assert_envelope_is_valid(events[0])
        assert events[0]["properties"]["usage_known"] is False
        run_seams.assert_not_called()

    @pytest.mark.usefixtures("run_seams")
    async def test_validation_sweeps_and_statistics_off_report_nothing(
        self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        router = mocker.AsyncMock()
        router.run = mocker.AsyncMock(side_effect=_succeed_untallied)
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTHON)
            await PipeRun(pipe_router=router, reports_usage_stats=False).run(pipe_job=_job(mocker=mocker, is_traced=True))
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTEST)
            await PipeRun(pipe_router=router).run(pipe_job=_job(mocker=mocker, is_traced=True))
            assert _debug_events(capsys.readouterr().err) == []

    @pytest.mark.parametrize(("router_run", "raised"), [(_call_then_succeed, None), (_call_then_fail, PipelexError)])
    @pytest.mark.usefixtures("run_seams")
    async def test_a_statistic_never_changes_the_runs_result(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        router_run: Any,
        raised: type[BaseException] | None,
    ) -> None:
        """A statistic that cannot be built, as when the state cannot be read, leaves the run to end as it would have."""
        mocker.patch.object(pipe_run_module, "report_run_usage", side_effect=OSError("a state that cannot be read"))
        router = mocker.AsyncMock()
        router.run = mocker.AsyncMock(side_effect=router_run)
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTHON)
            pipe_run = PipeRun(pipe_router=router)
            if raised is None:
                await pipe_run.run(pipe_job=_job(mocker=mocker, is_traced=True))
            else:
                with pytest.raises(raised):
                    await pipe_run.run(pipe_job=_job(mocker=mocker, is_traced=True))
            assert _debug_events(capsys.readouterr().err) == []
