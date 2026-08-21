import pytest
from pytest_mock import MockerFixture

from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget
from pipelex.pipe_run.exceptions import PipeRouterError, WebhookDeliveryError
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRun:
    async def test_run_success_with_delivery(self, mocker: MockerFixture) -> None:
        mock_output = mocker.MagicMock()
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(return_value=mock_output)

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-123", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        result = await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        assert result == mock_output
        mock_router.run.assert_called_once()
        mock_executor_instance.execute.assert_called_once()

    async def test_run_forwards_request_id_to_delivery_executor(self, mocker: MockerFixture) -> None:
        """Direct-mode PipeRun must forward pipe_job.job_metadata.run_metadata.request_id to DeliveryExecutor.execute.

        Parallel to the Temporal path (wf_pipe_run.py:108 → DeliveryActivityArg.request_id):
        without this forward, the storage/webhook completion logs lose correlation with the
        inbound X-Request-ID for non-Temporal pipeline runs.
        """
        mock_output = mocker.MagicMock()
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(return_value=mock_output)

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-req", storage_scope="test/scope"))
        mock_job.job_metadata.run_metadata.request_id = "req-direct-mode"

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        mock_executor_instance.execute.assert_called_once()
        call_kwargs = mock_executor_instance.execute.call_args.kwargs
        assert call_kwargs["request_id"] == "req-direct-mode"

    async def test_run_success_no_delivery_when_none(self, mocker: MockerFixture) -> None:
        """When delivery_assignment is None, the delivery executor is not called."""
        mock_output = mocker.MagicMock()
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(return_value=mock_output)

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-no-delivery", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)

        result = await pipe_run.run(pipe_job=mock_job)

        assert result == mock_output
        mock_executor_instance.execute.assert_not_called()

    async def test_run_failure_delivers_failed_status(self, mocker: MockerFixture) -> None:
        """On pipe execution failure, delivery runs with FAILED status, then error re-raises."""
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(
            side_effect=PipeRouterError(
                message="Pipe failed",
                run_mode=PipeRunMode.LIVE,
                pipe_code="test_pipe",
                output_name=None,
                pipe_stack=[],
            ),
        )

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-fail", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(PipeRouterError):
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        # Delivery should still have been called with FAILED status
        mock_executor_instance.execute.assert_called_once()
        call_kwargs = mock_executor_instance.execute.call_args.kwargs
        assert call_kwargs["status"] == "FAILED"
        assert call_kwargs["pipe_output"] is None

    async def test_run_failure_bare_exception_synthesizes_report(self, mocker: MockerFixture) -> None:
        """A bare (non-Pipelex) exception still delivers a structured error report.

        Direct mode must match Temporal mode, where ``recover_error_report`` is total:
        the FAILED webhook always carries an ``error`` object so receivers can
        rehydrate a failed run uniformly, whichever mode produced it.
        """
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=RuntimeError("router blew up"))

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-bare", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(RuntimeError, match="router blew up"):
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        mock_executor_instance.execute.assert_called_once()
        error_report = mock_executor_instance.execute.call_args.kwargs["error_report"]
        assert error_report is not None
        assert error_report.error_type == "PipelexUnexpectedError"
        assert "router blew up" in error_report.message

    async def test_run_failure_delivers_before_raising(self, mocker: MockerFixture) -> None:
        """Delivery runs BEFORE the error is re-raised."""
        call_order: list[str] = []

        mock_router = mocker.AsyncMock()

        async def failing_run(*_args: object, **_kwargs: object) -> None:  # ruff: ignore[unused-async]
            call_order.append("router.run")
            raise PipeRouterError(
                message="fail",
                run_mode=PipeRunMode.LIVE,
                pipe_code="p",
                output_name=None,
                pipe_stack=[],
            )

        mock_router.run = failing_run

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )

        async def mock_execute(*_args: object, **_kwargs: object) -> None:  # ruff: ignore[unused-async]
            call_order.append("delivery.execute")

        mock_executor.return_value.execute = mock_execute

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-order", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(PipeRouterError):
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        assert call_order == ["router.run", "delivery.execute"]

    async def test_run_failure_then_tracer_close_oserror_raises_original_error(self, mocker: MockerFixture) -> None:
        """When pipe fails AND close_tracer raises OSError, the original PipeRouterError is raised, not the OSError."""
        original_error = PipeRouterError(
            message="pipe blew up",
            run_mode=PipeRunMode.LIVE,
            pipe_code="test_pipe",
            output_name=None,
            pipe_stack=[],
        )
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=original_error)

        mock_tracer_manager = mocker.MagicMock()
        mock_tracer_manager.close_tracer = mocker.MagicMock(side_effect=OSError("disk full"))
        mocker.patch(
            "pipelex.pipe_run.pipe_run.GraphTracerManager.get_instance",
            return_value=mock_tracer_manager,
        )

        mock_executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor")
        mock_executor.return_value.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-mask-tracer", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)

        with pytest.raises(PipeRouterError) as exc_info:
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=DeliveryAssignment(storage=StorageTarget()))

        assert exc_info.value is original_error
        mock_tracer_manager.close_tracer.assert_called_once_with("plr-mask-tracer")

    async def test_run_success_with_tracer_close_oserror_propagates_oserror(self, mocker: MockerFixture) -> None:
        """When pipe succeeds but close_tracer raises OSError, OSError propagates (no prior error to preserve)."""
        mock_output = mocker.MagicMock()
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(return_value=mock_output)

        mock_tracer_manager = mocker.MagicMock()
        close_error = OSError("disk full")
        mock_tracer_manager.close_tracer = mocker.MagicMock(side_effect=close_error)
        mocker.patch(
            "pipelex.pipe_run.pipe_run.GraphTracerManager.get_instance",
            return_value=mock_tracer_manager,
        )

        mock_executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor")
        mock_executor.return_value.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-tracer-only", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)

        with pytest.raises(OSError, match="disk full") as exc_info:
            await pipe_run.run(pipe_job=mock_job)

        assert exc_info.value is close_error

    async def test_run_failure_with_tracer_and_delivery_failures_raises_original(self, mocker: MockerFixture) -> None:
        """Combined failure: pipe fails, tracer close fails, delivery fails — original PipeRouterError is raised."""
        original_error = PipeRouterError(
            message="pipe blew up",
            run_mode=PipeRunMode.LIVE,
            pipe_code="test_pipe",
            output_name=None,
            pipe_stack=[],
        )
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=original_error)

        mock_tracer_manager = mocker.MagicMock()
        mock_tracer_manager.close_tracer = mocker.MagicMock(side_effect=OSError("disk full"))
        mocker.patch(
            "pipelex.pipe_run.pipe_run.GraphTracerManager.get_instance",
            return_value=mock_tracer_manager,
        )

        mock_executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor")
        mock_executor.return_value.execute = mocker.AsyncMock(
            side_effect=WebhookDeliveryError("webhook 503"),
        )

        mock_job = mocker.MagicMock()
        # A real JobMetadata, not a MagicMock attribute: `PipeRun.run` copies it
        # onto the output, and `assemble_tracing_on_output` then feeds its
        # `run_metadata` into `TracingAssembly`, which is a typed field.
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-triple-fail", storage_scope="test/scope"))

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(PipeRouterError) as exc_info:
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        assert exc_info.value is original_error
        mock_tracer_manager.close_tracer.assert_called_once()
        mock_executor.return_value.execute.assert_called_once()
