"""``JobMetadata.log_context()`` is the one spelling of "bind this job's identifiers onto the log context".

The run half (``request_id`` and ``pipeline_run_id``) comes from ``run_metadata`` and the step half
(``pipe_run_id``) from the metadata itself. It is a ``bind_log_context`` block like any other: an absent
identifier inherits the outer binding rather than clearing it, and the previous binding comes back when
the block exits, whether it returns or raises.
"""

import pytest

from pipelex import log
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.log.log_context import LogContext, get_log_context


def _job_metadata(*, request_id: str | None = None, pipe_run_id: str | None = None) -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-job", request_id=request_id),
        pipe_run_id=pipe_run_id,
    )


class TestJobMetadataLogContext:
    def test_binds_the_run_identifiers_and_the_step_identifier(self) -> None:
        job_metadata = _job_metadata(request_id="req-job", pipe_run_id="pr-job")

        assert get_log_context() is None
        with job_metadata.log_context() as bound:
            assert bound == LogContext(request_id="req-job", pipeline_run_id="plr-job", pipe_run_id="pr-job")
            assert get_log_context() == bound
        assert get_log_context() is None

    def test_an_absent_identifier_inherits_the_outer_binding(self) -> None:
        """A submission's metadata carries no ``pipe_run_id``: binding it must not erase an enclosing step's."""
        with log.context(request_id="req-outer", pipe_run_id="pr-outer"), _job_metadata().log_context() as bound:
            assert bound == LogContext(request_id="req-outer", pipeline_run_id="plr-job", pipe_run_id="pr-outer")

    def test_the_previous_binding_comes_back_on_return_and_on_raise(self) -> None:
        job_metadata = _job_metadata(request_id="req-job", pipe_run_id="pr-job")
        outer = LogContext(pipeline_run_id="plr-outer", pipe_run_id="pr-outer")

        def explode() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        with log.context(pipeline_run_id="plr-outer", pipe_run_id="pr-outer"):
            with job_metadata.log_context():
                pass
            assert get_log_context() == outer

            with pytest.raises(RuntimeError, match="boom"), job_metadata.log_context():
                explode()
            assert get_log_context() == outer
