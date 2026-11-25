import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.problem import ProblemView
from pipelex.pipe_controllers.exceptions import PipeBatchTooWideError


def _make_error(*, started_item_count: int | None) -> PipeBatchTooWideError:
    return PipeBatchTooWideError(
        pipe_code="summarize_notes",
        input_list_label="notes",
        item_count=2000,
        estimated_bytes=56_000_000,
        estimated_events=12_000,
        bytes_left=48_000_000,
        events_left=50_000,
        max_fitting_item_count=1714,
        started_item_count=started_item_count,
    )


class TestPipeBatchTooWideError:
    @pytest.mark.parametrize(
        ("started_item_count", "expected_is_stopped", "expected_message"),
        [
            (
                None,
                False,
                (
                    "PipeBatch 'summarize_notes' was refused before any of its 2,000 items of 'notes' started: they would write "
                    "about 56,000,000 bytes and 12,000 events into the run's history, which has 48,000,000 bytes and 50,000 "
                    "events left for them. At most 1,714 items fit, so batch over a shorter list."
                ),
            ),
            (
                1500,
                True,
                (
                    "PipeBatch 'summarize_notes' was stopped after 1,500 of its 2,000 items of 'notes' started: the 500 items "
                    "left would write about 56,000,000 bytes and 12,000 events into the run's history, which has 48,000,000 "
                    "bytes and 50,000 events left for them. At most 1,714 items fit, so batch over a shorter list."
                ),
            ),
        ],
        ids=["refused_before_any_item", "stopped_after_some_items"],
    )
    def test_the_message_is_built_from_the_figures(self, started_item_count: int | None, expected_is_stopped: bool, expected_message: str) -> None:
        """Whichever backend raises it, the refusal words its figures the same way, and the stopped shape says how many started."""
        error = _make_error(started_item_count=started_item_count)

        assert error.message == expected_message
        assert str(error) == expected_message
        assert error.is_stopped is expected_is_stopped
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == (
            "Split the list 'notes' into lists of at most 1,714 items, each batched by a run of its own, or batch over fewer items."
        )

    @pytest.mark.parametrize("started_item_count", [None, 1500], ids=["refused_before_any_item", "stopped_after_some_items"])
    @pytest.mark.parametrize("view", [ProblemView.CALLER, ProblemView.OPERATOR])
    def test_the_problem_names_the_list_its_width_and_the_width_that_fits(self, started_item_count: int | None, view: ProblemView) -> None:
        """The problem is `input.too_large` on the batched list, the item count its `size` and the count that fits its `limit`."""
        error = _make_error(started_item_count=started_item_count)

        problem = error.to_problem(view=view)

        assert problem.code == CoreCode.INPUT_TOO_LARGE
        assert problem.params is not None
        assert problem.params.as_wire() == {"input": "notes", "limit": 1714, "size": 2000}
        assert problem.detail == "The input 'notes' reaches 2000, past the limit of 1714."
        assert problem.location is not None
        assert problem.location.input == "notes"
        if view.shows_diagnostics:
            assert problem.diagnostics is not None
            assert problem.diagnostics.message == error.message
        else:
            assert problem.diagnostics is None
