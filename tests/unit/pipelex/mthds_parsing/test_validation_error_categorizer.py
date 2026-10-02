import pytest

from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.validation_error_types import PipeValidationErrorType

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

# A misspelled field (`promtp`, pydantic's `extra_forbidden`, which no categorizer knows) in one pipe and
# an undeclared prompt variable in another.
_TYPO_BESIDE_UNDECLARED_VARIABLE_MTHDS = """
domain = "notes"
description = "Summarize and translate notes"

[pipe.summarize_notes]
type = "PipeLLM"
description = "Summarize the notes"
inputs = { notes = "Text" }
output = "Text"
promtp = "Summarize these notes"
prompt = "Summarize these notes: $notes"

[pipe.translate_notes]
type = "PipeLLM"
description = "Translate the notes"
inputs = { notes = "Text" }
output = "Text"
prompt = "Translate these notes into $language: $notes"
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
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=source)

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

    def test_an_uncategorized_error_is_kept_beside_a_categorized_one(self) -> None:
        """An error no categorizer knows is an item of its own, located by its source, pipe and field path."""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_TYPO_BESIDE_UNDECLARED_VARIABLE_MTHDS, mthds_source="notes.mthds")

        errors = exc_info.value.validation_errors
        assert len(errors) == 2
        typo_error = next(error for error in errors if error.error_type is None)
        assert typo_error.pipe_code == "summarize_notes"
        assert typo_error.domain_code == "notes"
        assert typo_error.source == "notes.mthds"
        # The union tag pydantic routed through (`PipeLLM`) is not a field of the bundle.
        assert typo_error.field_path == "pipe.summarize_notes.promtp"
        assert typo_error.message == "Validation error at 'pipe.summarize_notes.promtp': Extra inputs are not permitted"
        assert any(error.error_type == PipeValidationErrorType.MISSING_INPUT_VARIABLE for error in errors)

    @pytest.mark.parametrize("misspelled_key", ["prompt-template", "str"])
    def test_a_misspelled_key_is_named_whatever_it_looks_like(self, misspelled_key: str) -> None:
        """A key the author wrote stays in the field path even when it looks like one of pydantic's own elements."""
        mthds_content = _TYPO_BESIDE_UNDECLARED_VARIABLE_MTHDS.replace("promtp = ", f"{misspelled_key} = ")
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="notes.mthds")

        typo_error = next(error for error in exc_info.value.validation_errors if error.error_type is None)
        assert typo_error.field_path == f"pipe.summarize_notes.{misspelled_key}"
        assert typo_error.message == f"Validation error at 'pipe.summarize_notes.{misspelled_key}': Extra inputs are not permitted"

    def test_a_domain_that_is_not_a_string_locates_nothing(self) -> None:
        """The raw dict holds what the author wrote: a `domain = 123` is an error, never a locator."""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content='domain = 123\ndescription = "d"\n', mthds_source="numbers.mthds")

        (domain_error,) = exc_info.value.validation_errors
        assert domain_error.error_type is None
        assert domain_error.domain_code is None
        assert domain_error.source == "numbers.mthds"
        assert domain_error.field_path == "domain"

    def test_a_toml_syntax_error_carries_its_line_and_column(self) -> None:
        """Tomli counts both from 1, as the item's locators do."""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content='domain = "notes"\ndescription = "unterminated\n', mthds_source="notes.mthds")

        (syntax_error,) = exc_info.value.validation_errors
        assert (syntax_error.line, syntax_error.column) == (2, 28)
        assert syntax_error.source == "notes.mthds"
