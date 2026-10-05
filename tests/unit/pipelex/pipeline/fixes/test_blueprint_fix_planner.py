"""Unit tests for the blueprint-channel fix planner — enriched blueprint error data in, fix out.

``plan_fix_for_blueprint_validation_error`` is a pure translation keyed on ``error_type`` +
structured fields. The ``strip-native-concept-redecl`` rule fires only when the enrichment is
present — a ``NATIVE_CONCEPT_REDECLARATION`` error_type plus the offending ``concept_code`` set
by the single ``validate_concept_keys`` raise site — so other blueprint errors are suppressed
structurally. ``DELETE_KEY`` on ``["concept"]`` covers every authoring form (table, inline, dotted
all normalize to a ``concept.<Code>`` key).
"""

import pytest

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.fixes.planner import plan_fix_for_blueprint_validation_error
from pipelex.suggested_fix import DeleteKeyOp, FixSafety, RenameTableKeyOp, SetKeyOp, SuggestedFix
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


def _invalid_input_name_error_data(
    *,
    variable_name: str,
    redundant_input_name: str | None,
    pipe_code: str | None = "describe_page",
    dropped_input_marker: str | None = None,
) -> PipelexBundleBlueprintValidationErrorData:
    return PipelexBundleBlueprintValidationErrorData(
        error_type=PipeValidationErrorType.INVALID_INPUT_NAME,
        domain_code="catalog_review",
        source="main.mthds",
        pipe_code=pipe_code,
        variable_names=[variable_name],
        redundant_input_name=redundant_input_name,
        dropped_input_marker=dropped_input_marker,
        message=f"Input '{variable_name}' is not a plain input name.",
    )


_REDUNDANT_INPUT_BUNDLE_HEADER = """domain = "dotted_safety"
description = "Inputs declared once by their root and again by a dotted path into it"

[concept]
Item = "An item of an order"

[pipe.read_input]
type = "PipeLLM"
description = "Reads a field of its input"
output = "Text"
"""


def _fix_planned_from_inputs(input_specs: list[tuple[str, str]]) -> SuggestedFix:
    """The fix planned for a bundle whose one pipe declares these inputs, in this order, through the parser and its categorizer."""
    inputs_line = ", ".join(f'"{input_name}" = "{input_spec}"' for input_name, input_spec in input_specs)
    dotted_name = next(input_name for input_name, _ in input_specs if "." in input_name)
    mthds_content = f'{_REDUNDANT_INPUT_BUNDLE_HEADER}inputs = {{ {inputs_line} }}\nprompt = "Read ${dotted_name}"\n'
    with pytest.raises(MthdsParserError) as exc_info:
        MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="main.mthds")
    errors = exc_info.value.validation_errors
    assert len(errors) == 1, f"Expected exactly one error, got {[(error.error_type, error.message) for error in errors]}"
    assert errors[0].error_type == PipeValidationErrorType.INVALID_INPUT_NAME
    fix = plan_fix_for_blueprint_validation_error(errors[0])
    assert fix is not None
    assert fix.fix_code == "delete-redundant-dotted-input"
    return fix


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

    def test_redundant_dotted_input_yields_a_safe_delete_of_the_key(self) -> None:
        """R4: a dotted input whose root the same table declares is deleted from that pipe's `inputs`, safely."""
        fix = plan_fix_for_blueprint_validation_error(
            _invalid_input_name_error_data(variable_name="page.page_view", redundant_input_name="page.page_view")
        )
        assert fix is not None
        assert fix.fix_code == "delete-redundant-dotted-input"
        assert fix.safety == FixSafety.SAFE
        assert fix.source == "main.mthds"
        assert fix.ops == [DeleteKeyOp(table_path=["pipe", "describe_page", "inputs"], key="page.page_view")]
        assert "page.page_view" in fix.description

    def test_lone_dotted_input_yields_none(self) -> None:
        """R4: a lone dotted input carries no enrichment, since nothing says its root's concept: the author repairs it."""
        assert (
            plan_fix_for_blueprint_validation_error(_invalid_input_name_error_data(variable_name="page.page_view", redundant_input_name=None)) is None
        )

    def test_malformed_input_name_yields_none(self) -> None:
        """A malformed name is never deleted: its repair is a rename only the author can choose."""
        assert (
            plan_fix_for_blueprint_validation_error(_invalid_input_name_error_data(variable_name="InvoiceTotal", redundant_input_name=None)) is None
        )

    def test_redundant_dotted_input_without_its_pipe_yields_none(self) -> None:
        """Without the pipe the key lives in there is no table to delete it from."""
        error_data = _invalid_input_name_error_data(variable_name="page.page_view", redundant_input_name="page.page_view", pipe_code=None)
        assert plan_fix_for_blueprint_validation_error(error_data) is None

    def test_redundant_dotted_input_dropping_a_marker_yields_an_unsafe_delete_naming_it(self) -> None:
        """A deletion that would drop the key's marker from the root's contract is offered, but as UNSAFE, naming the marker and where to move it."""
        fix = plan_fix_for_blueprint_validation_error(
            _invalid_input_name_error_data(variable_name="data.text", redundant_input_name="data.text", dropped_input_marker="!")
        )
        assert fix is not None
        assert fix.fix_code == "delete-redundant-dotted-input"
        assert fix.safety == FixSafety.UNSAFE
        assert fix.ops == [DeleteKeyOp(table_path=["pipe", "describe_page", "inputs"], key="data.text")]
        assert "drops its marker `!`" in fix.description
        assert "move `!` onto 'data' if the root must carry it" in fix.description

    def test_redundant_dotted_input_dropping_its_plain_form_yields_an_unsafe_delete(self) -> None:
        """A key with no marker under a root that carries one is the same contract change seen from the other side: UNSAFE, naming the plain form."""
        fix = plan_fix_for_blueprint_validation_error(
            _invalid_input_name_error_data(variable_name="data.text", redundant_input_name="data.text", dropped_input_marker="")
        )
        assert fix is not None
        assert fix.safety == FixSafety.UNSAFE
        assert "drops its plain single form" in fix.description
        assert "declare 'data' without a marker if the root must be a plain single value" in fix.description

    @pytest.mark.parametrize(
        ("input_specs", "expected_safety", "deleted_key", "description_fragment"),
        [
            pytest.param(
                [("data", "Text?"), ("data.text", "Text!")],
                FixSafety.UNSAFE,
                "data.text",
                "drops its marker `!`, which 'data' does not carry: move `!` onto 'data' if the root must carry it",
                id="key-forcing-an-optional-root-declared-after-it",
            ),
            pytest.param(
                [("data.text", "Text!"), ("data", "Text?")],
                FixSafety.SAFE,
                "data.text",
                None,
                id="key-forcing-an-optional-root-declared-before-it",
            ),
            pytest.param(
                [("data", "Text!"), ("data.text", "Text!")],
                FixSafety.SAFE,
                "data.text",
                None,
                id="equal-markers",
            ),
            pytest.param(
                [("items", "Item"), ("items.x", "Text[]")],
                FixSafety.UNSAFE,
                "items.x",
                "drops its marker `[]`, which 'items' does not carry: move `[]` onto 'items' if the root must carry it",
                id="list-key-declared-after-its-single-root",
            ),
            pytest.param(
                [("items.x", "Text[]"), ("items", "Item")],
                FixSafety.SAFE,
                "items.x",
                None,
                id="list-key-declared-before-its-single-root",
            ),
            pytest.param(
                [("data", "Text?"), ("data.text", "Text")],
                FixSafety.UNSAFE,
                "data.text",
                "drops its plain single form",
                id="plain-key-declared-after-its-optional-root",
            ),
            pytest.param(
                [("page", "Page"), ("page.page_view", "Image")],
                FixSafety.SAFE,
                "page.page_view",
                None,
                id="differing-concept-root-first",
            ),
            pytest.param(
                [("page.page_view", "Image"), ("page", "Page")],
                FixSafety.SAFE,
                "page.page_view",
                None,
                id="differing-concept-root-last",
            ),
            pytest.param(
                [("data", "Text"), ("data.text", "Text[1]")],
                FixSafety.SAFE,
                "data.text",
                None,
                id="count-of-one-is-the-single-form",
            ),
            pytest.param(
                [("data", "Text?"), ("data.text", "Text!"), ("data.page", "Text?")],
                FixSafety.SAFE,
                "data.text",
                None,
                id="key-followed-by-another-under-its-root",
            ),
            pytest.param(
                [("data", "Text?"), ("data.text", "Text!"), ("page", "Page"), ("page.page_view", "Image")],
                FixSafety.SAFE,
                "page.page_view",
                None,
                id="safe-deletion-reported-before-an-unsafe-one",
            ),
        ],
    )
    def test_redundant_dotted_input_is_safe_to_delete_only_when_the_roots_contract_holds(
        self,
        input_specs: list[tuple[str, str]],
        expected_safety: FixSafety,
        deleted_key: str,
        description_fragment: str | None,
    ) -> None:
        """Deleting a dotted key beside its root is SAFE only when the root keeps the presence marker and multiplicity it had.

        Before dotted names were refused, every declaration under a root was folded onto that root in declaration order, so
        the last one set the root's presence marker and multiplicity. The concepts never decide: a field's concept differs
        from its root's by nature. With several keys under one root the table is read in order, and a SAFE deletion is
        reported before an UNSAFE one so the fix loop makes progress first.
        """
        fix = _fix_planned_from_inputs(input_specs)

        assert fix.safety == expected_safety
        assert fix.ops == [DeleteKeyOp(table_path=["pipe", "read_input", "inputs"], key=deleted_key)]
        if description_fragment is not None:
            assert description_fragment in fix.description
