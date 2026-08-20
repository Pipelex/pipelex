"""Unit tests for the blueprint-channel fix planner — enriched blueprint error data in, fix out.

``plan_fix_for_blueprint_validation_error`` is a pure translation keyed on ``error_type`` +
structured fields. The ``strip-native-concept-redecl`` rule fires only when the enrichment is
present — a ``NATIVE_CONCEPT_REDECLARATION`` error_type plus the offending ``concept_code`` set
by the single ``validate_concept_keys`` raise site — so other blueprint errors are suppressed
structurally. ``DELETE_KEY`` on ``["concept"]`` covers every authoring form (table, inline, dotted
all normalize to a ``concept.<Code>`` key).
"""

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.pipeline.fixes.planner import plan_fix_for_blueprint_validation_error
from pipelex.suggested_fix import DeleteKeyOp, FixSafety, RenameTableKeyOp, SetKeyOp
from pipelex.validation_error_types import PipeValidationErrorType


def _blueprint_error_data(
    *,
    error_type: PipeValidationErrorType | None = PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION,
    concept_code: str | None = "Text",
    source: str | None = "main.mthds",
) -> PipelexBundleBlueprintValidationErrorData:
    return PipelexBundleBlueprintValidationErrorData(
        error_type=error_type,
        domain_code="nativefix",
        source=source,
        concept_code=concept_code,
        message="Cannot declare a concept named 'Text' because it is natively available in Pipelex.",
    )


def _strip_namespace_error_data(
    *,
    pipe_code: str | None,
    stripped_pipe_code: str | None,
    source: str | None = "main.mthds",
) -> PipelexBundleBlueprintValidationErrorData:
    return PipelexBundleBlueprintValidationErrorData(
        error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
        domain_code="greetings",
        source=source,
        pipe_code=pipe_code,
        stripped_pipe_code=stripped_pipe_code,
        message="Pipe code 'greetings.hello' is not a valid pipe code. Must be in snake_case.",
    )


class TestBlueprintFixPlanner:
    def test_native_redeclaration_yields_strip_fix(self) -> None:
        """An enriched native-redeclaration error yields a SAFE delete_key of the concept."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data())
        assert fix is not None
        assert fix.fix_code == "strip-native-concept-redecl"
        assert fix.safety == FixSafety.SAFE
        assert fix.source == "main.mthds"
        assert fix.ops == [DeleteKeyOp(table_path=["concept"], key="Text")]
        assert "Text" in fix.description

    def test_fix_carries_the_offending_concept_code(self) -> None:
        """The deleted key is exactly the offending code, whatever it is."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data(concept_code="Number"))
        assert fix is not None
        assert fix.ops == [DeleteKeyOp(table_path=["concept"], key="Number")]

    def test_source_is_threaded_onto_the_fix(self) -> None:
        """A blueprint error's ``source`` rides the fix so the loop can target the declaring file."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data(source="sibling.mthds"))
        assert fix is not None
        assert fix.source == "sibling.mthds"

    def test_missing_source_still_yields_fix(self) -> None:
        """A single-file validation has no source; the fix still applies (source=None)."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data(source=None))
        assert fix is not None
        assert fix.source is None

    def test_missing_concept_code_yields_none(self) -> None:
        """Without the offending code there is no key to delete → no fix."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data(concept_code=None))
        assert fix is None

    def test_non_redeclaration_error_type_yields_none(self) -> None:
        """The planner is keyed on error_type: other blueprint errors never produce this fix."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data(error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX))
        assert fix is None

    def test_uncategorized_error_type_yields_none(self) -> None:
        """A blueprint error with no error_type (uncategorized residual) yields no fix."""
        fix = plan_fix_for_blueprint_validation_error(_blueprint_error_data(error_type=None))
        assert fix is None

    def test_dotted_declaration_yields_position_preserving_rename(self) -> None:
        """A strippable dotted declaration (pipe_code + stripped) yields a rename_table_key op."""
        error_data = _strip_namespace_error_data(pipe_code="greetings.hello", stripped_pipe_code="hello")
        fix = plan_fix_for_blueprint_validation_error(error_data)
        assert fix is not None
        assert fix.fix_code == "strip-namespace"
        assert fix.safety == FixSafety.SAFE
        assert fix.ops == [RenameTableKeyOp(table_path=["pipe"], key="greetings.hello", new_key="hello")]

    def test_dotted_main_pipe_yields_root_set_key(self) -> None:
        """A strippable main_pipe strip (no pipe_code) yields a set_key of main_pipe at the root."""
        error_data = _strip_namespace_error_data(pipe_code=None, stripped_pipe_code="hello")
        fix = plan_fix_for_blueprint_validation_error(error_data)
        assert fix is not None
        assert fix.fix_code == "strip-namespace"
        assert fix.ops == [SetKeyOp(table_path=[], key="main_pipe", value="hello")]

    def test_unstrippable_syntax_error_yields_none(self) -> None:
        """An INVALID_PIPE_CODE_SYNTAX error without ``stripped_pipe_code`` is not fixable."""
        error_data = _strip_namespace_error_data(pipe_code="Bad-Code", stripped_pipe_code=None)
        assert plan_fix_for_blueprint_validation_error(error_data) is None

    def test_strip_namespace_source_is_threaded(self) -> None:
        """The blueprint error's ``source`` rides the strip-namespace fix."""
        error_data = _strip_namespace_error_data(pipe_code="greetings.hello", stripped_pipe_code="hello", source="sibling.mthds")
        fix = plan_fix_for_blueprint_validation_error(error_data)
        assert fix is not None
        assert fix.source == "sibling.mthds"
