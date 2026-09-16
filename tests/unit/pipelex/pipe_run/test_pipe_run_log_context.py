"""Direct-mode ``PipeRun.run`` binds the log context from the job's own metadata.

The run-scoped identifiers travel in the payload; the contextvar is in-process plumbing bound at the
entry and released when the run returns, so a record emitted by anything the run calls carries them
and a record emitted after the run does not.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import pytest

from pipelex import log
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.log.log_context import LogContext, get_log_context

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _field(record: logging.LogRecord, *, name: str) -> Any:
    """A field carried on the record: an attribute the stdlib does not declare, read the way a sink reads it."""
    return getattr(record, name)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRunLogContext:
    async def test_run_binds_the_context_from_the_job_metadata(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        seen: dict[str, Any] = {}
        mock_output = mocker.MagicMock()

        async def observe(pipe_job: Any) -> Any:  # ruff: ignore[unused-function-argument]
            await asyncio.sleep(0)
            seen["context"] = get_log_context()
            log.info("inside the run")
            return mock_output

        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=observe)
        mock_job = mocker.MagicMock()
        mock_job.job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-ctx", storage_scope="test/scope", request_id="req-ctx"),
            pipe_run_id="pr-ctx",
        )

        assert get_log_context() is None
        with caplog.at_level(logging.INFO):
            result = await PipeRun(pipe_router=mock_router).run(pipe_job=mock_job)

        assert result == mock_output
        assert seen["context"] == LogContext(request_id="req-ctx", pipeline_run_id="plr-ctx", pipe_run_id="pr-ctx")
        assert get_log_context() is None
        (record,) = [record for record in caplog.records if record.name == __name__]
        assert _field(record, name="request_id") == "req-ctx"
        assert _field(record, name="pipeline_run_id") == "plr-ctx"
        assert _field(record, name="pipe_run_id") == "pr-ctx"

    async def test_run_binds_only_what_the_metadata_carries(self, mocker: MockerFixture) -> None:
        seen: dict[str, Any] = {}

        async def observe(pipe_job: Any) -> Any:  # ruff: ignore[unused-function-argument]
            await asyncio.sleep(0)
            seen["context"] = get_log_context()
            return mocker.MagicMock()

        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=observe)
        mock_job = mocker.MagicMock()
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-only", storage_scope="test/scope"))

        await PipeRun(pipe_router=mock_router).run(pipe_job=mock_job)

        assert seen["context"] == LogContext(pipeline_run_id="plr-only")
        assert seen["context"].fields == {"pipeline_run_id": "plr-only"}

    async def test_the_context_is_released_when_the_run_fails(self, mocker: MockerFixture) -> None:
        mock_router = mocker.AsyncMock()
        mock_router.run = mocker.AsyncMock(side_effect=RuntimeError("router blew up"))
        mock_job = mocker.MagicMock()
        mock_job.job_metadata = JobMetadata(run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-fail", storage_scope="test/scope"))

        with pytest.raises(RuntimeError):
            await PipeRun(pipe_router=mock_router).run(pipe_job=mock_job)

        assert get_log_context() is None
