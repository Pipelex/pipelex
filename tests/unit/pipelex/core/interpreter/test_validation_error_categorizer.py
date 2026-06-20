import pytest

from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeValidationErrorType

# A PipeBatch whose ``input_item_name`` equals its ``input_list_name`` — the collision
# ``PipeBatchBlueprint.validate_inputs`` raises as a ``PipeValidationError`` from inside a pydantic
# validator (pydantic wraps it as a ``value_error`` with the original in ``ctx["error"]``).
_PIPE_BATCH_COLLISION_MTHDS = """
domain = "batch_collision"
description = "PipeBatch input-name collision"

[concept]
Item = "an item"
Result = "a result"

[pipe.run_batch]
type = "PipeBatch"
description = "Batch over items"
inputs = { items = "Item[]" }
output = "Result[]"
branch_pipe_code = "process_item"
input_list_name = "items"
input_item_name = "items"
"""

# A PipeSequence step whose ``batch_over`` equals its ``batch_as`` — the collision
# ``SubPipeBlueprint.validate_batch_params`` raises (same wrapped-PipeValidationError shape, but
# nested deeper in the ``loc``: ``pipe.<code>.PipeSequence.steps.0``).
_SUB_PIPE_COLLISION_MTHDS = """
domain = "subpipe_collision"
description = "SubPipe batch_over/batch_as collision"

[concept]
Item = "an item"
Result = "a result"

[pipe.run_seq]
type = "PipeSequence"
description = "Sequence that batches a step over its own name"
inputs = { items = "Item[]" }
output = "Result"
steps = [
  { pipe = "process_one", batch_over = "items", batch_as = "items", result = "results" },
]
"""


class TestBlueprintValidationErrorCategorizer:
    @pytest.mark.parametrize(
        ("test_name", "mthds_content", "expected_pipe_code", "expected_domain_code"),
        [
            ("pipe_batch", _PIPE_BATCH_COLLISION_MTHDS, "run_batch", "batch_collision"),
            ("sub_pipe_sequence_step", _SUB_PIPE_COLLISION_MTHDS, "run_seq", "subpipe_collision"),
        ],
    )
    def test_wrapped_batch_collision_keeps_its_error_type(
        self,
        test_name: str,
        mthds_content: str,
        expected_pipe_code: str,
        expected_domain_code: str,
    ) -> None:
        """A blueprint-stage ``PipeValidationError`` is categorized with its ``error_type``, not dropped.

        Before the fix the blueprint categorizer did not unwrap the pydantic ``value_error`` wrapping a
        ``PipeValidationError``, so the batch-name collision degraded to an uncategorized residual
        (``error_type`` absent). Both raise sites (``PipeBatchBlueprint`` and the nested
        ``SubPipeBlueprint`` step) must now survive as a categorized ``batch_item_name_collision`` item
        carrying the ``pipe_code`` / ``domain_code`` / ``source`` locators recovered from the parse.
        """
        source = f"{test_name}.mthds"
        with pytest.raises(PipelexInterpreterError) as exc_info:
            PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=source)

        collision_items = [
            error for error in exc_info.value.validation_errors if error.error_type == PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
        ]
        assert len(collision_items) == 1, (
            f"Expected exactly one categorized batch_item_name_collision item, got error_types: "
            f"{[error.error_type for error in exc_info.value.validation_errors]}"
        )
        item = collision_items[0]
        assert item.pipe_code == expected_pipe_code
        assert item.domain_code == expected_domain_code
        assert item.source == source
        assert item.message, "The categorized item must carry the explanatory message"
        # The recovered message is the PipeValidationError's own clean text, not pydantic's
        # "Value error, " prefixed wrapper.
        assert not item.message.startswith("Value error"), f"Expected the unwrapped clean message, got: {item.message!r}"
