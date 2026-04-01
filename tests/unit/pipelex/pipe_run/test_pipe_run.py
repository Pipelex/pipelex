import pytest
from pytest_mock import MockerFixture

from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


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
        mock_job.job_metadata.pipeline_run_id = "plr-123"

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        result = await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        assert result == mock_output
        mock_router.run.assert_called_once()
        mock_executor_instance.execute.assert_called_once()

    async def test_run_success_default_delivery(self, mocker: MockerFixture) -> None:
        """When no delivery_assignment is provided, default storage-only delivery runs."""
        mock_output = mocker.MagicMock()
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(return_value=mock_output)

        mock_executor = mocker.patch(
            "pipelex.pipe_run.pipe_run.DeliveryExecutor",
        )
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()

        mock_job = mocker.MagicMock()
        mock_job.job_metadata.pipeline_run_id = "plr-default"

        pipe_run = PipeRun(pipe_router=mock_router)

        result = await pipe_run.run(pipe_job=mock_job)

        assert result == mock_output
        mock_executor_instance.execute.assert_called_once()
        call_kwargs = mock_executor_instance.execute.call_args.kwargs
        assert call_kwargs["delivery_assignment"].storage is not None

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
        mock_job.job_metadata.pipeline_run_id = "plr-fail"

        pipe_run = PipeRun(pipe_router=mock_router)

        with pytest.raises(PipeRouterError):
            await pipe_run.run(pipe_job=mock_job)

        # Delivery should still have been called with FAILED status
        mock_executor_instance.execute.assert_called_once()
        call_kwargs = mock_executor_instance.execute.call_args.kwargs
        assert call_kwargs["status"] == "FAILED"
        assert call_kwargs["pipe_output"] is None

    async def test_run_failure_delivers_before_raising(self, mocker: MockerFixture) -> None:
        """Delivery runs BEFORE the error is re-raised."""
        call_order: list[str] = []

        mock_router = mocker.AsyncMock()

        async def failing_run(*_args: object, **_kwargs: object) -> None:  # noqa: RUF029
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

        async def mock_execute(*_args: object, **_kwargs: object) -> None:  # noqa: RUF029
            call_order.append("delivery.execute")

        mock_executor.return_value.execute = mock_execute

        mock_job = mocker.MagicMock()
        mock_job.job_metadata.pipeline_run_id = "plr-order"

        pipe_run = PipeRun(pipe_router=mock_router)

        with pytest.raises(PipeRouterError):
            await pipe_run.run(pipe_job=mock_job)

        assert call_order == ["router.run", "delivery.execute"]
