import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.pipe_controllers.batch.pipe_batch import warn_of_large_batch
from pipelex.tools.log.log_fields import USER_ACTION_FIELD
from pipelex.urls import URLs


class TestPipeBatchLargeBatchAdvisory:
    @pytest.mark.parametrize(
        ("max_concurrency", "expected_bound_fields"),
        [(8, {"max_concurrency": 8}), (None, {})],
        ids=["bounded", "unbounded"],
    )
    def test_the_advisory_is_one_event_whose_bound_is_a_field(
        self, mocker: MockerFixture, max_concurrency: int | None, expected_bound_fields: dict[str, object]
    ) -> None:
        """The advisory said "with bounded fan-out" even when the configuration's `"unbounded"` set no bound at all.

        Bounded or not, the fan-out is one event under one message, its bound a field absent when there is none.
        """
        warning_spy = mocker.patch.object(log, "warning")

        warn_of_large_batch(pipe_code="summarize_each", item_count=250, max_concurrency=max_concurrency)

        warning_spy.assert_called_once_with(
            "A PipeBatch fans out over a large list without durable execution",
            fields={
                "pipe_code": "summarize_each",
                "item_count": 250,
                **expected_bound_fields,
                "url.full": URLs.durable_execution,
                USER_ACTION_FIELD: "Consider a durable execution backend for rate-limited, resumable runs",
            },
        )
