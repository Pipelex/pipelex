"""Pin: a native-concept redeclaration carries structured error data (autofix enrichment).

Declaring a concept whose code collides with a native Pipelex concept (`Text`, `Number`, …) is
illegal. The ``validate_concept_keys`` before-validator knows the offending code at detection
time; these tests pin that the blueprint error data carries a dedicated
``NATIVE_CONCEPT_REDECLARATION`` ``error_type`` and the offending ``concept_code`` as a structured
field — across every authoring form (table, table + structure sub-table, string shorthand, dotted)
— instead of leaving the code buried in the message text. This enriched fact is what the fix
planner translates into a ``strip-native-concept-redecl`` suggested fix.
"""

from collections.abc import Callable

import pytest

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType

_REDECL_TABLE_MTHDS = """
domain = "nativefix_table"
main_pipe = "make_report"

[concept.Report]
description = "A report."

# Illegal: redeclares the native Text concept as a table.
[concept.Text]
description = "Redeclared native Text."

[pipe.make_report]
type = "PipeLLM"
description = "Make a report."
inputs = { topic = "Text" }
output = "Report"
prompt = "Write a report about $topic"
"""

_REDECL_TABLE_STRUCTURE_MTHDS = """
domain = "nativefix_struct"
main_pipe = "make_report"

[concept.Report]
description = "A report."

# Illegal: redeclares the native Text concept, with a structure sub-table.
[concept.Text]
description = "Redeclared native Text."

[concept.Text.structure]
body = { type = "text", description = "The body." }

[pipe.make_report]
type = "PipeLLM"
description = "Make a report."
inputs = { topic = "Text" }
output = "Report"
prompt = "Write a report about $topic"
"""

_REDECL_STRING_SHORTHAND_MTHDS = """
domain = "nativefix_inline"
main_pipe = "make_note"

[concept]
Note = "A short note."
# Illegal: redeclares the native Text concept as a string shorthand.
Text = "Redeclared native Text."

[pipe.make_note]
type = "PipeLLM"
description = "Make a note."
inputs = { topic = "Text" }
output = "Note"
prompt = "Write a note about $topic"
"""

_REDECL_DOTTED_MTHDS = """
domain = "nativefix_dotted"
main_pipe = "make_memo"

concept.Memo = "A memo."
# Illegal: redeclares the native Number concept via a dotted key.
concept.Number = "Redeclared native Number."

[pipe.make_memo]
type = "PipeLLM"
description = "Make a memo."
inputs = { count = "Number" }
output = "Memo"
prompt = "Write a memo with $count items"
"""


async def _redeclaration_error(mthds_content: str) -> PipelexBundleBlueprintValidationErrorData:
    """Validate a redeclaration bundle and return the first native-redeclaration blueprint error."""
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[mthds_content])
    matching = [
        error_data
        for error_data in exc_info.value.pipelex_bundle_blueprint_validation_errors
        if error_data.error_type == PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION
    ]
    assert matching, (
        f"Expected a NATIVE_CONCEPT_REDECLARATION error, got "
        f"{[(e.error_type, e.concept_code) for e in exc_info.value.pipelex_bundle_blueprint_validation_errors]}"
    )
    return matching[0]


@pytest.mark.asyncio(loop_scope="class")
class TestNativeConceptRedeclEnrichment:
    @pytest.mark.parametrize(
        ("mthds_content", "expected_concept_code"),
        [
            (_REDECL_TABLE_MTHDS, "Text"),
            (_REDECL_TABLE_STRUCTURE_MTHDS, "Text"),
            (_REDECL_STRING_SHORTHAND_MTHDS, "Text"),
            (_REDECL_DOTTED_MTHDS, "Number"),
        ],
    )
    async def test_redeclaration_carries_concept_code(
        self,
        load_empty_library: Callable[[], str],
        mthds_content: str,
        expected_concept_code: str,
    ) -> None:
        """Every authoring form of a native-concept redeclaration carries the offending code."""
        load_empty_library()
        error_data = await _redeclaration_error(mthds_content)
        assert error_data.concept_code == expected_concept_code

    async def test_invalid_concept_code_is_not_a_redeclaration(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A syntactically invalid concept code is a different failure — not a native redeclaration.

        Only the native-collision raise site is typed; the invalid-syntax branch stays a bare
        ``ValueError`` (uncategorized), so it must never masquerade as a fixable redeclaration.
        """
        load_empty_library()
        invalid_code_mthds = """
domain = "nativefix_invalid"
main_pipe = "noop"

[concept]
"not a valid code" = "Bad concept code."

[pipe.noop]
type = "PipeLLM"
description = "Noop."
inputs = { topic = "Text" }
output = "Text"
prompt = "Do nothing with $topic"
"""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[invalid_code_mthds])
        redeclaration_errors = [
            error_data
            for error_data in exc_info.value.pipelex_bundle_blueprint_validation_errors
            if error_data.error_type == PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION
        ]
        assert not redeclaration_errors
