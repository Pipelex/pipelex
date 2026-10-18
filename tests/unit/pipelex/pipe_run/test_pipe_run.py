import logging
from contextlib import AbstractContextManager, nullcontext
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import PipelexProblem
from pipelex.pipe_run import pipe_run as pipe_run_module
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, StorageTarget, WebhookTarget
from pipelex.pipe_run.exceptions import PipeRouterError, WebhookDeliveryError
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

_WEBHOOK_URL = "https://hooks.example.test/runs"


class _UnbuildableProblemError(PipelexError):
    """A run's error whose problem cannot be built: its parameters raise, as a faulty override in a plugin's error could."""

    error_code = CoreCode.INPUT_INVALID

    @override
    def problem_params(self) -> dict[str, Any]:
        msg = "the parameters could not be read"
        raise RuntimeError(msg)


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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-123", storage_scope="test/scope", read_scope=None)
        )

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(
                user_id="pytest",
                pipeline_run_id="plr-req",
                storage_scope="test/scope",
                read_scope=None,
                request_id="req-direct-mode",
            )
        )

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        mock_executor_instance.execute.assert_called_once()
        call_kwargs = mock_executor_instance.execute.call_args.kwargs
        assert call_kwargs["request_id"] == "req-direct-mode"

    @pytest.mark.parametrize(
        ("router_error", "expected_status"),
        [
            (None, DeliveryStatus.COMPLETED),
            (RuntimeError("router blew up"), DeliveryStatus.FAILED),
        ],
    )
    async def test_the_delivery_is_logged_at_debug_with_its_status(
        self,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        router_error: Exception | None,
        expected_status: DeliveryStatus,
    ) -> None:
        """A user's log says whether delivery ran and for which outcome; the run context stamps the run id."""
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(return_value=mocker.MagicMock(), side_effect=router_error)
        mock_executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor")
        mock_executor.return_value.execute = mocker.AsyncMock()
        mock_job = mocker.MagicMock()
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-delivery-log", storage_scope="test/scope", read_scope=None)
        )

        expectation: AbstractContextManager[Any] = pytest.raises(RuntimeError, match="router blew up") if router_error is not None else nullcontext()
        with expectation, caplog.at_level(logging.DEBUG, logger=pipe_run_module.__name__):
            await PipeRun(pipe_router=mock_router).run(pipe_job=mock_job, delivery_assignment=DeliveryAssignment(storage=StorageTarget()))

        delivery_records = [
            record for record in caplog.records if record.name == pipe_run_module.__name__ and record.getMessage() == "Executing the delivery"
        ]
        assert len(delivery_records) == 1
        delivery_record = delivery_records[0]
        assert delivery_record.levelno == logging.DEBUG
        record_fields = vars(delivery_record)
        assert record_fields.get("delivery_status") == expected_status
        assert record_fields.get("pipeline_run_id") == "plr-delivery-log"

    async def test_the_failure_line_names_the_pipe_as_the_pipe_run_lines_do(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        """`pipe_code` carried the qualified reference here and the bare code on `Pipe run starts`, so one query missed this line."""
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=RuntimeError("router blew up"))
        mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor")
        mock_job = mocker.MagicMock()
        mock_job.pipe.code = "describe_company"
        mock_job.pipe.pipe_ref = "company.describe_company"
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-failure-line", storage_scope="test/scope", read_scope=None)
        )

        with pytest.raises(RuntimeError, match="router blew up"), caplog.at_level(logging.ERROR, logger=pipe_run_module.__name__):
            await PipeRun(pipe_router=mock_router).run(pipe_job=mock_job)

        (failure_record,) = [
            record for record in caplog.records if record.name == pipe_run_module.__name__ and record.getMessage() == "The execution of a pipe failed"
        ]
        record_fields = vars(failure_record)
        assert record_fields["pipe_code"] == "describe_company"
        assert record_fields["pipe_ref"] == "company.describe_company"
        assert record_fields["error.type"] == "RuntimeError"
        assert record_fields["error.message"] == "router blew up"
        assert failure_record.exc_info is None

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-no-delivery", storage_scope="test/scope", read_scope=None)
        )

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-fail", storage_scope="test/scope", read_scope=None)
        )

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(PipeRouterError):
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        # Delivery should still have been called with FAILED status
        mock_executor_instance.execute.assert_called_once()
        call_kwargs = mock_executor_instance.execute.call_args.kwargs
        assert call_kwargs["status"] == "FAILED"
        assert call_kwargs["pipe_output"] is None

    async def test_run_failure_bare_exception_synthesizes_problem(self, mocker: MockerFixture) -> None:
        """A bare (non-Pipelex) exception still delivers a problem, a fault of ours.

        Direct mode must match Temporal mode, where the recovered problem is total:
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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-bare", storage_scope="test/scope", read_scope=None)
        )

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget(), webhooks=[WebhookTarget(url=_WEBHOOK_URL)])

        with pytest.raises(RuntimeError, match="router blew up"):
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        mock_executor_instance.execute.assert_called_once()
        problem = mock_executor_instance.execute.call_args.kwargs["problem"]
        assert isinstance(problem, PipelexProblem)
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.pipeline_run_id == "plr-bare"
        # The problem is the operator's, which each webhook projects to its own view.
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "PipelexUnexpectedError"
        assert problem.diagnostics.message == "RuntimeError: router blew up"

    @pytest.mark.parametrize(
        "assignment",
        [
            pytest.param(None, id="no_delivery"),
            pytest.param(DeliveryAssignment(storage=StorageTarget()), id="no_webhook"),
            pytest.param(DeliveryAssignment(webhooks=[WebhookTarget(url=_WEBHOOK_URL)]), id="webhook"),
        ],
    )
    async def test_a_problem_that_cannot_be_built_never_replaces_the_run_s_error(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture, assignment: DeliveryAssignment | None
    ) -> None:
        """The run fails with its own error; the problem is built only for a webhook, and one that raises is a fault of ours."""
        run_error = _UnbuildableProblemError("the pipe refused its input")
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=run_error)
        mock_executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor")
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute = mocker.AsyncMock()
        mock_job = mocker.MagicMock()
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-unbuildable", storage_scope="test/scope", read_scope=None)
        )

        with pytest.raises(_UnbuildableProblemError) as raised, caplog.at_level(logging.ERROR, logger=pipe_run_module.__name__):
            await PipeRun(pipe_router=mock_router).run(pipe_job=mock_job, delivery_assignment=assignment)

        assert raised.value is run_error
        fault_records = [record for record in caplog.records if record.getMessage() == pipe_run_module.WEBHOOK_PROBLEM_FAULT_MESSAGE]
        if assignment is None:
            mock_executor_instance.execute.assert_not_called()
            assert fault_records == []
            return
        problem = mock_executor_instance.execute.call_args.kwargs["problem"]
        if not assignment.webhooks:
            assert problem is None
            assert fault_records == []
            return
        assert isinstance(problem, PipelexProblem)
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.pipeline_run_id == "plr-unbuildable"
        (fault_record,) = fault_records
        assert vars(fault_record)["failed_error_type"] == "_UnbuildableProblemError"

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-order", storage_scope="test/scope", read_scope=None)
        )

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-mask-tracer", storage_scope="test/scope", read_scope=None)
        )

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-tracer-only", storage_scope="test/scope", read_scope=None)
        )

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
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-triple-fail", storage_scope="test/scope", read_scope=None)
        )

        pipe_run = PipeRun(pipe_router=mock_router)
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(PipeRouterError) as exc_info:
            await pipe_run.run(pipe_job=mock_job, delivery_assignment=assignment)

        assert exc_info.value is original_error
        mock_tracer_manager.close_tracer.assert_called_once()
        mock_executor.return_value.execute.assert_called_once()
