from typing import Any

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.binding.binding_step_blueprint import check_binding_step_shape
from pipelex.validation_error_types import PipeValidationErrorType

_STEP_LABEL = "Step 1 of pipe 'index_catalog'"


def _shape_refusal(*, raw_step: dict[str, Any]) -> str:
    with pytest.raises(PipeValidationError) as exc_info:
        check_binding_step_shape(raw_step=raw_step, step_label=_STEP_LABEL)
    assert exc_info.value.error_type == PipeValidationErrorType.BINDING_STEP_INVALID
    return str(exc_info.value)


class TestBindingStepShape:
    @pytest.mark.parametrize(
        ("stray_fields", "joined_fields"),
        [
            pytest.param({"batch_over": "lines"}, "cannot carry `batch_over`.", id="one-field"),
            pytest.param({"batch_over": "lines", "batch_as": "line"}, "cannot carry `batch_over` or `batch_as`.", id="two-fields"),
            pytest.param(
                {"nb_output": 2, "batch_over": "lines", "batch_as": "line"},
                "cannot carry `nb_output`, `batch_over` or `batch_as`.",
                id="three-fields",
            ),
            pytest.param(
                {"nb_output": 2, "multiple_output": True, "batch_over": "lines", "batch_as": "line"},
                "cannot carry `nb_output`, `multiple_output`, `batch_over` or `batch_as`.",
                id="four-fields",
            ),
        ],
    )
    def test_the_stray_fields_are_joined_in_prose(self, stray_fields: dict[str, Any], joined_fields: str) -> None:
        message = _shape_refusal(raw_step={"from": "invoice.lines", "result": "lines", **stray_fields})

        assert f"{_STEP_LABEL} is a binding step (it carries `from`), which carries only `from` and `result`, so it {joined_fields}" in message

    @pytest.mark.parametrize(
        "stray_fields",
        [
            pytest.param({"batch_over": "lines", "batch_as": "line"}, id="both-batch-fields"),
            pytest.param({"batch_as": "line"}, id="batch-as-alone"),
        ],
    )
    def test_a_dotted_from_proposes_the_dotted_batch_over_that_binds_it(self, stray_fields: dict[str, Any]) -> None:
        message = _shape_refusal(raw_step={"from": "invoice.lines", "result": "lines", **stray_fields})

        assert (
            'To batch over the list at `invoice.lines`, write `batch_over = "invoice.lines"` on the pipe step to run once per item: a dotted '
            "`batch_over` binds the list at that path and batches over it. "
            'Or keep this step as `{ from = "invoice.lines", result = "lines" }` and batch over `lines` in the next pipe step.'
        ) in message
        assert "a plain `batch_over`" not in message

    def test_a_bare_from_proposes_a_plain_batch_that_binds_nothing(self) -> None:
        message = _shape_refusal(raw_step={"from": "pages", "result": "page_list", "batch_over": "page_list", "batch_as": "page"})

        assert (
            'To batch over `pages`, write `batch_over = "pages"` on the pipe step to run once per item: a plain `batch_over` batches over '
            'that name and needs no binding. Or keep this step as `{ from = "pages", result = "page_list" }` and batch over `page_list` in '
            "the next pipe step."
        ) in message
        assert "binds the list" not in message

    @pytest.mark.parametrize(
        "result",
        [
            pytest.param(None, id="without-result"),
            pytest.param(3, id="a-result-that-is-not-a-string"),
        ],
    )
    def test_the_remedy_names_a_placeholder_without_a_string_result(self, result: Any) -> None:
        raw_step: dict[str, Any] = {"from": "invoice.lines", "batch_over": "lines"}
        if result is not None:
            raw_step["result"] = result

        message = _shape_refusal(raw_step=raw_step)

        assert 'Or keep this step as `{ from = "invoice.lines", result = "<name>" }` and batch over `<name>` in the next pipe step.' in message

    @pytest.mark.parametrize(
        "stray_fields",
        [
            pytest.param({"nb_output": 2}, id="nb-output"),
            pytest.param({"multiple_output": True}, id="multiple-output"),
            pytest.param({"nb_output": 2, "multiple_output": True}, id="both-count-fields"),
        ],
    )
    def test_a_stray_count_proposes_no_batch(self, stray_fields: dict[str, Any]) -> None:
        message = _shape_refusal(raw_step={"from": "invoice.lines", "result": "lines", **stray_fields})

        assert (
            "`nb_output` and `multiple_output` set how many outputs a pipe produces, so they go on the pipe step running that pipe: "
            "a binding step binds the value as it is."
        ) in message
        assert "batch_over" not in message

    def test_both_families_of_fields_get_both_remedies(self) -> None:
        message = _shape_refusal(raw_step={"from": "invoice.lines", "result": "lines", "multiple_output": True, "batch_over": "lines"})

        assert "To batch over the list at `invoice.lines`" in message
        assert "`nb_output` and `multiple_output` set how many outputs a pipe produces" in message
