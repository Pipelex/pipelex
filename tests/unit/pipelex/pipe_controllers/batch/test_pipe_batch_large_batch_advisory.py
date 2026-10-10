import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.pipe_controllers.batch.pipe_batch import warn_of_large_batch
from pipelex.urls import URLs


class TestPipeBatchLargeBatchAdvisory:
    @pytest.mark.parametrize(
        ("max_concurrency", "expected_message", "expected_fields"),
        [
            (
                8,
                (
                    "A PipeBatch fans out over a large list with bounded fan-out, which is backpressure and not durable execution; "
                    "for a workload this size, consider a durable execution backend for rate-limited, resumable runs"
                ),
                {"pipe_code": "summarize_each", "item_count": 250, "max_concurrency": 8, "url.full": URLs.durable_execution},
            ),
            (
                None,
                (
                    "A PipeBatch fans out over a large list with unbounded fan-out, which is neither backpressure nor durable execution; "
                    "for a workload this size, consider a durable execution backend for rate-limited, resumable runs"
                ),
                {"pipe_code": "summarize_each", "item_count": 250, "url.full": URLs.durable_execution},
            ),
        ],
        ids=["bounded", "unbounded"],
    )
    def test_the_advisory_says_what_the_fan_out_is(
        self, mocker: MockerFixture, max_concurrency: int | None, expected_message: str, expected_fields: dict[str, object]
    ) -> None:
        """The advisory said "with bounded fan-out" even when the configuration's `"unbounded"` set no bound at all."""
        warning_spy = mocker.patch.object(log, "warning")

        warn_of_large_batch(pipe_code="summarize_each", item_count=250, max_concurrency=max_concurrency)

        warning_spy.assert_called_once_with(expected_message, fields=expected_fields)
