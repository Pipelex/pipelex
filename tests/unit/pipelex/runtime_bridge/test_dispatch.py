import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError, PipelexBridgeDispatchError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.temporal.exceptions import WorkflowExecutionError


def _make_fake_pipe_job(mocker: MockerFixture, pipe_code: str, pipeline_run_id: str) -> PipeJob:
    """Build a PipeJob without triggering Pydantic's PipeAbstract validation.

    Tests at the dispatch layer don't care about the concrete pipe — only
    that the bridge routes the right pipe_job to the right PipeRun. Using
    ``model_construct`` lets us pass a MagicMock as ``pipe`` without
    constructing a full PipeAbstract subclass.
    """
    fake_pipe = mocker.MagicMock()
    fake_pipe.code = pipe_code
    fake_pipe.domain_code = "fake_domain"
    return PipeJob.model_construct(
        pipe=fake_pipe,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(user_id="anonymous", pipeline_run_id=pipeline_run_id),
        library_crate=None,
    )


@pytest.mark.asyncio
class TestDispatch:
    async def test_direct_mode_calls_pipe_run_with_pipe_job(self, mocker: MockerFixture) -> None:
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        fake_output = PipeOutput(
            working_memory=WorkingMemoryFactory.make_empty(),
            pipeline_run_id="injected-run-id",
        )
        mock_run = mocker.patch.object(PipeRun, "run", new_callable=mocker.AsyncMock, return_value=fake_output)

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code="fake_pipe",
                execution_mode=PipelexExecutionMode.DIRECT,
                pipeline_run_id="caller-run-id",
            )
        )

        assert mock_run.await_count == 1
        await_args = mock_run.await_args
        assert await_args is not None
        call_kwargs: dict[str, object] = dict(await_args.kwargs)
        assert call_kwargs["delivery_assignment"] is None
        assert call_kwargs["pipe_job"] is fake_job

        assert result.is_completed is True
        assert result.pipeline_run_id == "injected-run-id"
        assert result.workflow_id is None
        assert result.graph_spec_dump is None

    async def test_temporal_blocking_dispatches_to_temporal_pipe_run(self, mocker: MockerFixture) -> None:
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        fake_output = PipeOutput(
            working_memory=WorkingMemoryFactory.make_empty(),
            pipeline_run_id="temporal-run-id",
        )
        fake_temporal_run = mocker.AsyncMock(return_value=fake_output)
        fake_factory = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.make_temporal_pipe_run")
        fake_factory.return_value.run = fake_temporal_run
        # The bridge reports the actual Temporal workflow id (make_workflow_id, which prefixes by run
        # mode), not the bare pipeline_run_id. Stub it to a known value and assert the bridge surfaces it.
        fake_factory.return_value.make_workflow_id.return_value = "ut-temporal-run-id"

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code="fake_pipe",
                execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING,
            )
        )

        fake_factory.assert_called_once()
        assert fake_temporal_run.await_count == 1
        fake_factory.return_value.make_workflow_id.assert_called_once_with(pipeline_run_id="caller-run-id")
        assert result.is_completed is True
        assert result.workflow_id == "ut-temporal-run-id"

    async def test_temporal_blocking_failure_wraps_in_dispatch_error_preserving_report(self, mocker: MockerFixture) -> None:
        """A Temporal-mode pipe failure surfaces as WorkflowExecutionError, which the bridge wraps into
        the uniform PipelexBridgeDispatchError (same contract as DIRECT/mistral). The structured
        ErrorReport is not lost: it stays reachable via __cause__, and PipelexBridgeDispatchError's
        to_error_report() surfaces the underlying classification via cause-chain enrichment.
        """
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        report = ErrorReport(
            error_type="CogtError",
            message="rate limited on the worker",
            title="AI inference failed",
            type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
            error_category="capacity",
            error_domain=ErrorDomain.RUNTIME,
            retryable=False,
            model="gpt-5",
            provider="openai",
        )
        workflow_failure = WorkflowExecutionError(report.message, error_report=report)
        fake_factory = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.make_temporal_pipe_run")
        fake_factory.return_value.run = mocker.AsyncMock(side_effect=workflow_failure)

        with pytest.raises(PipelexBridgeDispatchError) as exc_info:
            await run_pipe_via_bridge(
                PipelexPipeRunInput(
                    pipe_code="fake_pipe",
                    execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING,
                )
            )

        # The raw Temporal failure is preserved as the cause...
        assert exc_info.value.__cause__ is workflow_failure
        # ...and the structured classification is surfaced through the wrapper's report.
        recovered = exc_info.value.to_error_report()
        assert recovered.error_type == "PipelexBridgeDispatchError"
        assert recovered.error_category == "capacity"
        assert recovered.retryable is False
        assert recovered.model == "gpt-5"
        assert recovered.provider == "openai"

    async def test_temporal_fire_and_forget_returns_workflow_id_without_completion(self, mocker: MockerFixture) -> None:
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        fake_handle = mocker.MagicMock()
        fake_start = mocker.AsyncMock(return_value=("wf-id-42", fake_handle))
        fake_factory = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.make_temporal_pipe_run")
        fake_factory.return_value.start = fake_start

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code="fake_pipe",
                execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
                delivery_assignment_dump={"webhooks": [{"url": "https://example.test/hook"}], "storage": None},
                pipeline_run_id="caller-run-id",
            )
        )

        fake_start.assert_awaited_once()
        assert result.is_completed is False
        assert result.workflow_id == "wf-id-42"
        assert result.pipeline_run_id == "caller-run-id"
        assert result.output_dict == {}

    async def test_mistral_native_without_plugin_raises_with_install_hint(self, mocker: MockerFixture) -> None:
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        # MISTRAL_NATIVE is contributed by the external pipelex-mistralai-workflows plugin, which is
        # not installed in core's test env — so the orchestrator registry has no entry for it and the
        # bridge raises MissingOrchestratorError, which maps the mode to its exact install hint.
        with pytest.raises(MissingOrchestratorError) as exc_info:
            await run_pipe_via_bridge(
                PipelexPipeRunInput(
                    pipe_code="fake_pipe",
                    execution_mode=PipelexExecutionMode.MISTRAL_NATIVE,
                )
            )

        assert exc_info.value.mode is PipelexExecutionMode.MISTRAL_NATIVE
        assert "pipelex-mistralai-workflows" in str(exc_info.value)
        assert "pip install" in str(exc_info.value)
