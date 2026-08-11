"""Pin: wiring/concept/type failures surface as STRUCTURED, categorized validation_errors[].

Three failure modes used to collapse to a bare message-only residual (no ``error_type``,
no locator). They now carry a category + ``error_type`` + identity locators, built by the
one shared builder and projected onto ``ErrorReport.validation_errors`` (the same items the
agent CLI emits and the hosted ``InvalidReport`` carries):

- pipe-owned unresolved concept reference (a pipe input/output) → ``pipe_validation`` /
  ``unresolved_concept`` (with the referencing pipe, the missing concept, and the field).
- concept-owned unresolved concept reference (a concept's ``refines`` or a structure field's
  ``concept_ref``) → ``blueprint_validation`` / ``unresolved_concept`` (with the owning concept),
  so a concept-level failure is never bucketed as a phantom pipe error with a null pipe_code.
- undefined pipe dependency → ``pipe_validation`` / ``unresolved_pipe_dependency`` (with the
  referencing pipe in ``pipe_code`` and the missing dependency in ``missing_pipe_code``).
- unknown pipe ``type`` (a pydantic discriminated-union tag failure) → categorized
  ``blueprint_validation`` / ``unknown_pipe_type`` with the pipe locator.

Also pins the categorizer fix that made the ``pipe_code`` locator actually populate on
categorized pipe-blueprint items (the loc key is ``pipe``, not ``pipes``).
"""

from collections.abc import Callable

import pytest

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

_UNKNOWN_CONCEPT_MTHDS = """
domain = "structured_unknown_concept"
main_pipe = "make_thing"

[pipe.make_thing]
type = "PipeLLM"
description = "Produce an undeclared concept."
inputs = { topic = "Text" }
output = "NonExistentConcept"
prompt = "Write a paragraph about $topic"
"""

_MISSING_DEPENDENCY_MTHDS = """
domain = "structured_missing_dep"
main_pipe = "do_two_steps"

[pipe.do_two_steps]
type = "PipeSequence"
description = "Two-step sequence whose second step does not exist."
inputs = { text = "Text" }
output = "Text"
steps = [
  { pipe = "first_step", result = "interim" },
  { pipe = "second_step_missing", result = "final" },
]

[pipe.first_step]
type = "PipeLLM"
description = "Echo the text."
inputs = { text = "Text" }
output = "Text"
prompt = "Repeat verbatim: $text"
"""

_UNKNOWN_PIPE_TYPE_MTHDS = """
domain = "structured_bad_pipe_type"
main_pipe = "mystery"

[pipe.mystery]
type = "PipeWizardry"
description = "Not a real pipe type."
inputs = { text = "Text" }
output = "Text"
prompt = "Do something magical with $text"
"""

_TYPELESS_IMPL_FIELD_MTHDS = """
domain = "structured_typeless_impl"
main_pipe = "summarize_doc"

[pipe.summarize_doc]
description = "Looks like an implementation but names no type."
inputs = { doc = "Text" }
output = "Text"
prompt = "Summarize $doc."
"""

_EXPLICIT_SIGNATURE_TAG_MTHDS = """
domain = "structured_explicit_sig_tag"
main_pipe = "summarize_doc"

[pipe.summarize_doc]
type = "PipeSignature"
description = "Still writes the retired tag."
inputs = { doc = "Text" }
output = "Text"
"""

_PROMPT_INPUT_MISMATCH_MTHDS = """
domain = "structured_prompt_mismatch"
main_pipe = "greet_person"

[pipe.greet_person]
type = "PipeLLM"
description = "Greeting whose prompt uses an undeclared variable."
inputs = { name = "Text" }
output = "Text"
prompt = "Write a greeting for $name who lives in $city."
"""

_EXTRANEOUS_INPUT_MTHDS = """
domain = "structured_extraneous_input"
main_pipe = "greet_person"

[pipe.greet_person]
type = "PipeLLM"
description = "Greeting that declares an input the prompt never uses."
inputs = { name = "Text", unused_thing = "Text" }
output = "Text"
prompt = "Write a greeting for $name."
"""

_CONCEPT_OWNED_UNRESOLVED_MTHDS = """
domain = "structured_concept_owned"
main_pipe = "use_wrapper"

[concept]
Wrapper = { description = "Wraps a missing base concept.", refines = "MissingBase" }

[pipe.use_wrapper]
type = "PipeLLM"
description = "Produce a wrapper."
inputs = { text = "Text" }
output = "Wrapper"
prompt = "Describe $text"
"""


async def _validation_errors_for(mthds_contents: str) -> list[ValidationErrorItem]:
    """Validate one invalid bundle and return its structured validation_errors[]."""
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[mthds_contents])
    report = exc_info.value.to_error_report()
    items = report.validation_errors
    assert items, "Every invalid verdict must carry a non-empty validation_errors[]"
    return items


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleStructuredErrors:
    async def test_unresolved_concept_is_a_categorized_pipe_validation_item(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        items = await _validation_errors_for(_UNKNOWN_CONCEPT_MTHDS)
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"Expected an unresolved_concept item, got {[(i.category, i.error_type) for i in items]}"
        item = concept_items[0]
        assert item.category == ValidationErrorCategory.PIPE_VALIDATION
        assert item.pipe_code == "make_thing"
        assert item.concept_code == "NonExistentConcept"
        assert item.field_name == "output"
        assert item.domain_code == "structured_unknown_concept"

    async def test_concept_owned_unresolved_concept_is_a_categorized_blueprint_item(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A concept-owned ref (here a `refines`) surfaces as a blueprint_validation item on the OWNING
        concept, not as a phantom pipe_validation item with a null pipe_code.
        """
        load_empty_library()
        items = await _validation_errors_for(_CONCEPT_OWNED_UNRESOLVED_MTHDS)
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"Expected an unresolved_concept item, got {[(i.category, i.error_type) for i in items]}"
        item = concept_items[0]
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.pipe_code is None
        assert item.concept_code == "Wrapper"
        assert item.domain_code == "structured_concept_owned"
        assert "MissingBase" in item.message

    async def test_unresolved_pipe_dependency_is_a_categorized_pipe_validation_item(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """`missing_pipe_code` names the ref that was actually tried — the QUALIFIED one.

        The author wrote `second_step_missing`; the compiler read it as
        `structured_missing_dep.second_step_missing`, because a bare ref names its own domain. Reporting
        the bare spelling back would hide the only interesting part. This field is a structured field
        machine consumers read, so its value changing is a wire-visible change, not a cosmetic one.
        """
        load_empty_library()
        items = await _validation_errors_for(_MISSING_DEPENDENCY_MTHDS)
        dependency_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY]
        assert dependency_items, f"Expected an unresolved_pipe_dependency item, got {[(i.category, i.error_type) for i in items]}"
        item = dependency_items[0]
        assert item.category == ValidationErrorCategory.PIPE_VALIDATION
        assert item.pipe_code == "do_two_steps"
        assert item.missing_pipe_code == "structured_missing_dep.second_step_missing"
        # The message has to bridge the gap between what they wrote and what was tried, or it names a
        # pipe that appears nowhere in their file and reads like a compiler bug.
        assert "structured_missing_dep.second_step_missing" in item.message
        assert "own domain" in item.message

    async def test_unknown_pipe_type_is_a_categorized_blueprint_item(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        items = await _validation_errors_for(_UNKNOWN_PIPE_TYPE_MTHDS)
        type_items = [item for item in items if item.error_type == PipeValidationErrorType.UNKNOWN_PIPE_TYPE]
        assert type_items, f"Expected an unknown_pipe_type item, got {[(i.category, i.error_type) for i in items]}"
        item = type_items[0]
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.pipe_code == "mystery"
        assert item.domain_code == "structured_bad_pipe_type"

    async def test_typeless_pipe_with_impl_field_is_a_categorized_blueprint_item(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A typeless pipe that declares an implementation field (`prompt`) surfaces as a categorized
        blueprint item with the MISSING_PIPE_TYPE error_type and the pipe locator — not a bare residual.
        """
        load_empty_library()
        items = await _validation_errors_for(_TYPELESS_IMPL_FIELD_MTHDS)
        type_items = [item for item in items if item.error_type == PipeValidationErrorType.MISSING_PIPE_TYPE]
        assert type_items, f"Expected a missing_pipe_type item, got {[(i.category, i.error_type) for i in items]}"
        item = type_items[0]
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.pipe_code == "summarize_doc"
        assert item.domain_code == "structured_typeless_impl"
        assert "prompt" in item.message

    async def test_explicit_signature_tag_is_a_categorized_blueprint_item(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A section that writes the retired `type = "PipeSignature"` tag DECLARED a type — it is just
        no longer a valid one — so it surfaces as UNKNOWN_PIPE_TYPE (a declared-but-invalid type), not
        MISSING_PIPE_TYPE, with the pipe locator and the migration guidance in the message.
        """
        load_empty_library()
        items = await _validation_errors_for(_EXPLICIT_SIGNATURE_TAG_MTHDS)
        type_items = [item for item in items if item.error_type == PipeValidationErrorType.UNKNOWN_PIPE_TYPE]
        assert type_items, f"Expected an unknown_pipe_type item, got {[(i.category, i.error_type) for i in items]}"
        item = type_items[0]
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.pipe_code == "summarize_doc"
        assert item.domain_code == "structured_explicit_sig_tag"
        assert "is no longer a pipe type" in item.message
        # It is NOT miscategorized as "missing" — the pipe declared a type.
        assert not [item for item in items if item.error_type == PipeValidationErrorType.MISSING_PIPE_TYPE]

    async def test_missing_input_variable_now_carries_the_pipe_code_locator(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Regression for the categorizer loc-key fix: pipe_code now populates on pipe blueprint items."""
        load_empty_library()
        items = await _validation_errors_for(_PROMPT_INPUT_MISMATCH_MTHDS)
        missing_items = [item for item in items if item.error_type == PipeValidationErrorType.MISSING_INPUT_VARIABLE]
        assert missing_items, f"Expected a missing_input_variable item, got {[(i.category, i.error_type) for i in items]}"
        item = missing_items[0]
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.pipe_code == "greet_person"
        assert item.variable_names == ["city"]

    async def test_pipe_channel_items_stay_domain_qualified(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Every item that carries a `pipe_code` must carry `domain_code` too — the
        presentation chain identifies pipes by full ref (`domain_code.pipe_code`), so a
        bare-code item degrades node decorations and click-to-navigate downstream. Pins
        the report-wide invariant on an extraneous-input bundle (surfaced here by the
        blueprint categorizer; the operator-raised `PipeValidationError` sites that used
        to omit `domain_code` are fixed at their raise sites and pinned by the pipe-sorter
        unit test).
        """
        load_empty_library()
        items = await _validation_errors_for(_EXTRANEOUS_INPUT_MTHDS)
        extraneous_items = [item for item in items if item.error_type == PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE]
        assert extraneous_items, f"Expected an extraneous_input_variable item, got {[(i.category, i.error_type) for i in items]}"
        item = extraneous_items[0]
        assert item.pipe_code == "greet_person"
        assert item.domain_code == "structured_extraneous_input"
        # The invariant holds across the whole report, not just the pinned channel.
        for reported in items:
            if reported.pipe_code is not None:
                assert reported.domain_code is not None, f"item {reported.error_type} carries pipe_code without domain_code"
