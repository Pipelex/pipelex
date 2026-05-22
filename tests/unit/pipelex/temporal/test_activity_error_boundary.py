"""Unit test for ``convert_pipelex_errors`` — the activity-side half of the Temporal error bridge.

Pins the invariants the decorator relies on:

- ``functools.wraps`` preserves ``__name__`` and ``__annotations__``. Both are
  load-bearing: Temporal's ``@activity.defn`` reads the annotations for payload
  typing, and ``content_generator_in_workflow.py`` reads ``__name__`` for dispatch
  routing. A future refactor that drops ``functools.wraps`` would break silently
  without this test.
- A ``PipelexError`` raised by the wrapped activity comes out as a ``TemporalError``.
- A non-``PipelexError`` propagates untouched, for Temporal's default converter.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors
from pipelex.temporal.tprl.temporal_error import TemporalError


async def sample_activity(value: int) -> int:  # noqa: RUF029
    """Stand-in activity body — exercises the success path and signature preservation."""
    return value * 2


async def raises_pipelex_error() -> None:  # noqa: RUF029
    """Stand-in activity body that fails with a ``PipelexError``."""
    msg = "simulated activity failure"
    raise PipelexError(msg)


async def raises_value_error() -> None:  # noqa: RUF029
    """Stand-in activity body that fails with a non-``PipelexError`` exception."""
    msg = "not a pipelex error"
    raise ValueError(msg)


@pytest.mark.asyncio(loop_scope="class")
class TestConvertPipelexErrors:
    @pytest.fixture(autouse=True)
    def log_mocks(self, mocker: MockerFixture) -> None:
        """Silence the bridge log helpers — they require a live Temporal context."""
        mocker.patch.object(TemporalError, "_log_critical")
        mocker.patch.object(TemporalError, "_log_error")

    async def test_preserves_signature_and_passes_success_through(self) -> None:
        """``functools.wraps`` keeps ``__name__``/``__annotations__`` and the success value flows through."""
        wrapped = convert_pipelex_errors(sample_activity)

        assert wrapped.__name__ == "sample_activity", "Temporal and workflow-side dispatch routing read __name__"
        assert wrapped.__annotations__ == sample_activity.__annotations__, "Temporal reads __annotations__ for payload typing"
        assert await wrapped(21) == 42

    async def test_pipelex_error_becomes_temporal_error(self) -> None:
        """A ``PipelexError`` raised inside the activity is converted to a ``TemporalError``
        that chains the original cause and packs the structured ``ErrorReport``.
        """
        wrapped = convert_pipelex_errors(raises_pipelex_error)

        with pytest.raises(TemporalError) as exc_info:
            await wrapped()

        temporal_error = exc_info.value
        assert isinstance(temporal_error.__cause__, PipelexError), "the original PipelexError must be chained as __cause__"
        assert temporal_error.error_report is not None, "the decorator must pack the structured ErrorReport into the TemporalError"
        assert temporal_error.error_report["message"] == "simulated activity failure"

    async def test_non_pipelex_error_propagates_untouched(self) -> None:
        """A non-``PipelexError`` is left for Temporal's default converter — not wrapped."""
        wrapped = convert_pipelex_errors(raises_value_error)

        with pytest.raises(ValueError, match="not a pipelex error"):
            await wrapped()
