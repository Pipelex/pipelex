"""The run-scoped log context: the identifiers every record emitted in scope carries.

The identifiers travel in the payload (``JobMetadata`` for a direct-mode run, the request or the
activity argument at a process entry elsewhere); a process entry binds them here with
:func:`bind_log_context`, and the dispatch stamps them onto every record until the block exits. The
contextvar is in-process plumbing after deserialization and nothing else: it never crosses a process
boundary, and a record emitted outside any bound context carries none of the identifiers.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Generator

# The reserved identifier names. They are spelled exactly as the payload fields they come from, the
# job metadata's and the run result's, so a record and the run it relates to agree on the key.
REQUEST_ID_FIELD = "request_id"
PIPELINE_RUN_ID_FIELD = "pipeline_run_id"
PIPE_RUN_ID_FIELD = "pipe_run_id"


class LogContext(BaseModel):
    """The identifiers bound for a scope. An absent identifier is ``None`` here and absent from the record."""

    model_config = ConfigDict(frozen=True)

    request_id: str | None = None
    pipeline_run_id: str | None = None
    pipe_run_id: str | None = None

    @property
    def fields(self) -> dict[str, str]:
        """The bound identifiers as record attributes: only the ones that are set, never the string ``"None"``."""
        fields: dict[str, str] = {}
        if self.request_id is not None:
            fields[REQUEST_ID_FIELD] = self.request_id
        if self.pipeline_run_id is not None:
            fields[PIPELINE_RUN_ID_FIELD] = self.pipeline_run_id
        if self.pipe_run_id is not None:
            fields[PIPE_RUN_ID_FIELD] = self.pipe_run_id
        return fields

    def merged_with(
        self,
        *,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        pipe_run_id: str | None = None,
    ) -> LogContext:
        """A copy where each given identifier overrides this one's and a ``None`` inherits it."""
        return LogContext(
            request_id=request_id if request_id is not None else self.request_id,
            pipeline_run_id=pipeline_run_id if pipeline_run_id is not None else self.pipeline_run_id,
            pipe_run_id=pipe_run_id if pipe_run_id is not None else self.pipe_run_id,
        )


_log_context_var: ContextVar[LogContext | None] = ContextVar("pipelex_log_context", default=None)


def get_log_context() -> LogContext | None:
    """The context bound for the current task, or ``None`` outside any ``bind_log_context`` block."""
    return _log_context_var.get()


@contextmanager
def bind_log_context(
    *,
    request_id: str | None = None,
    pipeline_run_id: str | None = None,
    pipe_run_id: str | None = None,
) -> Generator[LogContext]:
    """Bind the identifiers for the duration of the block, merged over whatever is already bound.

    Nested blocks merge, the inner one overriding the outer for the identifiers it gives, and the exit
    restores the previous binding whether the block returns or raises. A contextvar is task-local, so
    concurrent asyncio tasks each keep their own binding.
    """
    current = _log_context_var.get() or LogContext()
    bound = current.merged_with(request_id=request_id, pipeline_run_id=pipeline_run_id, pipe_run_id=pipe_run_id)
    token = _log_context_var.set(bound)
    try:
        yield bound
    finally:
        _log_context_var.reset(token)
