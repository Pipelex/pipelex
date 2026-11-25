from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.problem import ProblemView
from pipelex.pipe_controllers.exceptions import PipeBatchTooWideError

_REFUSED_FOOTPRINT = (
    "PipeBatch 'summarize_notes' was refused before any of its 2,000 items of 'notes' started: they would write "
    "about 56,000,000 bytes and 12,000 events into the run's history, which has 48,000,000 bytes and 50,000 "
    "events left for them."
)
_STOPPED_FOOTPRINT = (
    "PipeBatch 'summarize_notes' was stopped after 1,500 of its 2,000 items of 'notes' started: the 500 items "
    "left would write about 56,000,000 bytes and 12,000 events into the run's history, which has 48,000,000 "
    "bytes and 50,000 events left for them."
)
_SOME_FIT_SENTENCE = "At most 1,714 items fit, so batch over a shorter list."
_NONE_FIT_SENTENCE = "Not even one item fits, so make each item, and what the branch pipe reads besides it, smaller."
_SOME_FIT_ADVICE = "Split the list 'notes' into lists of at most 1,714 items, each batched by a run of its own, or batch over fewer items."
_NONE_FIT_ADVICE = "Make each item of the list 'notes', and what the branch pipe reads besides it, smaller."


def _make_error(*, started_item_count: int | None, max_fitting_item_count: int) -> PipeBatchTooWideError:
    return PipeBatchTooWideError(
        pipe_code="summarize_notes",
        input_list_label="notes",
        item_count=2000,
        estimated_bytes=56_000_000,
        estimated_events=12_000,
        bytes_left=48_000_000,
        events_left=50_000,
        max_fitting_item_count=max_fitting_item_count,
        started_item_count=started_item_count,
    )


class TestPipeBatchTooWideError:
    @pytest.mark.parametrize(
        ("started_item_count", "max_fitting_item_count", "expected_is_stopped", "expected_message", "expected_advice"),
        [
            (None, 1714, False, f"{_REFUSED_FOOTPRINT} {_SOME_FIT_SENTENCE}", _SOME_FIT_ADVICE),
            (1500, 1714, True, f"{_STOPPED_FOOTPRINT} {_SOME_FIT_SENTENCE}", _SOME_FIT_ADVICE),
            (None, 0, False, f"{_REFUSED_FOOTPRINT} {_NONE_FIT_SENTENCE}", _NONE_FIT_ADVICE),
            (1500, 0, True, f"{_STOPPED_FOOTPRINT} {_NONE_FIT_SENTENCE}", _NONE_FIT_ADVICE),
        ],
        ids=["refused_some_fit", "stopped_some_fit", "refused_none_fit", "stopped_none_fit"],
    )
    def test_the_message_is_built_from_the_figures(
        self,
        started_item_count: int | None,
        max_fitting_item_count: int,
        expected_is_stopped: bool,
        expected_message: str,
        expected_advice: str,
    ) -> None:
        """Whichever backend raises it, the refusal words its figures the same way.

        The stopped shape says how many items started, and a refusal where no item fits asks for smaller items.
        """
        error = _make_error(started_item_count=started_item_count, max_fitting_item_count=max_fitting_item_count)

        assert error.message == expected_message
        assert str(error) == expected_message
        assert error.is_stopped is expected_is_stopped
        assert error.fits_no_item is (max_fitting_item_count == 0)
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == expected_advice

    @pytest.mark.parametrize(
        ("max_fitting_item_count", "expected_params", "expected_detail"),
        [
            (1714, {"input": "notes", "limit": 1714, "size": 2000}, "The input 'notes' reaches 2000, past the limit of 1714."),
            (0, {"input": "notes", "size": 2000}, "The input 'notes' reaches 2000, past what the step that reads it accepts."),
        ],
        ids=["some_fit", "none_fit"],
    )
    @pytest.mark.parametrize("started_item_count", [None, 1500], ids=["refused", "stopped"])
    @pytest.mark.parametrize("view", [ProblemView.CALLER, ProblemView.OPERATOR])
    def test_the_problem_names_the_list_its_width_and_the_width_that_fits(
        self,
        started_item_count: int | None,
        max_fitting_item_count: int,
        expected_params: dict[str, Any],
        expected_detail: str,
        view: ProblemView,
    ) -> None:
        """`input.too_large` on the batched list: the item count its `size` and the count that fits its `limit`, withheld when none fits.

        The unit suite's autouse sweep fails the test if building the problem logs a missing required parameter, so a
        withheld `limit` is shown to be withheld by rule rather than lacking.
        """
        error = _make_error(started_item_count=started_item_count, max_fitting_item_count=max_fitting_item_count)

        problem = error.to_problem(view=view)

        assert problem.code == CoreCode.INPUT_TOO_LARGE
        assert problem.params is not None
        assert problem.params.as_wire() == expected_params
        assert problem.detail == expected_detail
        assert problem.location is not None
        assert problem.location.input == "notes"
        if view.shows_diagnostics:
            assert problem.diagnostics is not None
            assert problem.diagnostics.message == error.message
        else:
            assert problem.diagnostics is None
