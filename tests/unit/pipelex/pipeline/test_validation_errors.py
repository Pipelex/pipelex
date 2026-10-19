"""Unit tests for ``build_validation_error_items`` — the shared structured-error builder.

The single builder feeds the problem's ``errors`` (via ``ValidateBundleError.problem_items``), which the agent CLI
prints, and the API's invalid verdict (``BundleValidationFailure.validation_errors``, via
``ValidateBundleError.validation_error_items``), so the surfaces can never drift. These tests pin the per-category
field projection, including the ``source`` / ``field_name`` / ``concept_code`` fields, and that the problem's errors
follow the builder's items one for one.
"""

import json

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validation_errors import build_validation_error_items, warning_problem_items
from pipelex.suggested_fix import DeleteKeyOp, RenameTableKeyOp, SetKeyOp
from pipelex.validation_error_types import HintLintErrorType, PipeFactoryErrorType, PipeValidationErrorType, TemplateCheckErrorType


def _build_items(exc: ValidateBundleError) -> list[ValidationErrorItem]:
    """Call the builder with the error's categorized lists only — for the category-projection tests.

    The pipe-validation arm uses ``pipe_validation_error_data`` (pipe validation **plus**
    pipe/concept instantiation errors) — the same combined accessor the real call site
    (``ValidateBundleError.validation_error_items``, which the problem's items and the API verdict both read) passes.
    The dry-run failures and the ``fallback_message`` residual are intentionally omitted here so these
    tests pin the categorized projection in isolation; they have their own dedicated tests below.
    """
    return build_validation_error_items(
        blueprint_errors=exc.pipelex_bundle_blueprint_validation_errors,
        factory_errors=exc.pipe_factory_errors,
        pipe_validation_errors=exc.pipe_validation_error_data,
    )


def _all_category_error() -> ValidateBundleError:
    return ValidateBundleError(
        message="validation failed",
        pipelex_bundle_blueprint_validation_errors=[
            PipelexBundleBlueprintValidationErrorData(
                error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                domain_code="testapp",
                source="sibling.mthds",
                pipe_code="pipe_a",
                concept_code="Customer",
                message="missing var x",
                variable_names=["x"],
            ),
        ],
        pipe_factory_errors=[
            PipeFactoryErrorData(
                error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
                domain_code="testapp",
                pipe_code="pipe_b",
                missing_concept_code="Foo",
                declared_concepts=["Bar", "Baz"],
                message="concept Foo not found",
            ),
        ],
        pipe_validation_errors=[
            PipesAndConceptValidationErrorData(
                error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                domain_code="testapp",
                source="main.mthds",
                pipe_code="pipe_c",
                concept_code="Order",
                field_name="inputs",
                message="extra var y",
                field_path="pipe_c.inputs.y",
                variable_names=["y"],
            ),
        ],
    )


class TestBuildValidationErrorItems:
    def test_covers_all_three_categories_in_order(self) -> None:
        """The builder emits one item per underlying error, blueprint → factory → pipe-validation."""
        items = _build_items(_all_category_error())
        assert [item.category for item in items] == [
            ValidationErrorCategory.BLUEPRINT_VALIDATION,
            ValidationErrorCategory.PIPE_FACTORY,
            ValidationErrorCategory.PIPE_VALIDATION,
        ]

    def test_blueprint_item_carries_source_and_identity(self) -> None:
        """Blueprint errors now surface ``source`` and ``concept_code`` (dropped by the old extractor)."""
        blueprint_item = _build_items(_all_category_error())[0]
        assert blueprint_item.source == "sibling.mthds"
        assert blueprint_item.concept_code == "Customer"
        assert blueprint_item.pipe_code == "pipe_a"
        assert blueprint_item.domain_code == "testapp"
        assert blueprint_item.error_type == PipeValidationErrorType.MISSING_INPUT_VARIABLE
        assert blueprint_item.variable_names == ["x"]
        # Factory-only fields stay unset for a blueprint error.
        assert blueprint_item.missing_concept_code is None
        assert blueprint_item.declared_concepts is None

    def test_factory_item_keeps_missing_concept_and_declared_concepts(self) -> None:
        """The factory-only fields the old extractor emitted are preserved by the shared builder."""
        factory_item = _build_items(_all_category_error())[1]
        assert factory_item.category == ValidationErrorCategory.PIPE_FACTORY
        assert factory_item.missing_concept_code == "Foo"
        assert factory_item.declared_concepts == ["Bar", "Baz"]
        # Factory errors have no source / field_path.
        assert factory_item.source is None
        assert factory_item.field_path is None

    def test_pipe_validation_item_carries_source_field_name_and_field_path(self) -> None:
        """Pipe/concept-validation errors surface ``source`` and ``field_name`` alongside ``field_path``."""
        pipe_item = _build_items(_all_category_error())[2]
        assert pipe_item.source == "main.mthds"
        assert pipe_item.field_name == "inputs"
        assert pipe_item.field_path == "pipe_c.inputs.y"
        assert pipe_item.concept_code == "Order"
        assert pipe_item.variable_names == ["y"]

    def test_empty_error_yields_no_items(self) -> None:
        """A ValidateBundleError with no categorized lists builds an empty list."""
        assert _build_items(ValidateBundleError(message="no details")) == []

    def test_each_dry_run_failure_becomes_a_located_dry_run_item(self) -> None:
        """Each pipe whose dry run failed yields its own ``dry_run`` item, located on that pipe."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[],
            dry_run_failures=[
                DryRunFailureErrorData(
                    code=CoreCode.METHOD_WIRING_INVALID,
                    pipe_code="analyze",
                    domain_code="probe",
                    source="probe.mthds",
                    message="Pipe 'analyze' failed its dry run: x",
                ),
                DryRunFailureErrorData(
                    code=CoreCode.RUNTIME_UNEXPECTED, pipe_code="publish", domain_code="probe", message="Pipe 'publish' failed its dry run: y"
                ),
            ],
        )
        assert [item.category for item in items] == [ValidationErrorCategory.DRY_RUN, ValidationErrorCategory.DRY_RUN]
        assert all(item.error_type == "DryRunError" for item in items)
        assert (items[0].pipe_code, items[0].domain_code, items[0].source) == ("analyze", "probe", "probe.mthds")
        assert items[0].message == "Pipe 'analyze' failed its dry run: x"
        assert (items[1].pipe_code, items[1].source) == ("publish", None)

    def test_dry_run_items_ride_beside_categorized_items(self) -> None:
        """A dry-run failure is kept beside a categorized error: no channel hides another."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[
                PipeFactoryErrorData(
                    error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
                    pipe_code="pipe_x",
                    missing_concept_code="Foo",
                    message="concept Foo not found",
                ),
            ],
            pipe_validation_errors=[],
            dry_run_failures=[
                DryRunFailureErrorData(
                    code=CoreCode.METHOD_WIRING_INVALID, pipe_code="pipe_y", domain_code="dom", message="Pipe 'pipe_y' failed its dry run: z"
                )
            ],
        )
        assert [item.category for item in items] == [ValidationErrorCategory.PIPE_FACTORY, ValidationErrorCategory.DRY_RUN]

    def test_a_verdict_projects_its_dry_run_failures(self) -> None:
        """A ``ValidateBundleError`` carrying dry-run failures lists one ``dry_run`` item per failure, and its problem one item each."""
        exc = ValidateBundleError(
            message="Dry run failed",
            dry_run_failures=[
                DryRunFailureErrorData(
                    code=CoreCode.METHOD_WIRING_INVALID, pipe_code="analyze", domain_code="probe", message="Pipe 'analyze' failed its dry run: x"
                )
            ],
        )
        assert [item.category for item in exc.validation_error_items()] == [ValidationErrorCategory.DRY_RUN]
        assert exc.message == "Pipe 'analyze' failed its dry run: x"
        problem = exc.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert problem.errors is not None
        assert [(item.code, item.location.pipe if item.location else None) for item in problem.errors] == [
            (CoreCode.METHOD_WIRING_INVALID, "analyze")
        ]

    def test_fallback_message_residual_becomes_single_blueprint_item(self) -> None:
        """A parse-level failure (only a message, no categorized data) yields one ``blueprint_validation`` item.

        This is the most common failure — a malformed ``.mthds`` file (TOML syntax, an empty
        blueprint, a bundle elaborator). The bundle could not be turned into a blueprint at all, so
        ``blueprint_validation`` is the right bucket. It is parse-level, so it has no ``source``, and
        ``error_type`` stays ``None`` (the message is authoritative).
        """
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[],
            fallback_message="TOML syntax error at line 3, column 1: unclosed table header",
        )
        assert [item.category for item in items] == [ValidationErrorCategory.BLUEPRINT_VALIDATION]
        assert items[0].message == "TOML syntax error at line 3, column 1: unclosed table header"
        assert items[0].error_type is None
        assert items[0].source is None

    def test_dry_run_items_win_over_fallback_message(self) -> None:
        """The fallback residual is a last resort: a dry-run item leaves it unused."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[],
            dry_run_failures=[
                DryRunFailureErrorData(code=CoreCode.METHOD_WIRING_INVALID, pipe_code="analyze", message="Pipe 'analyze' failed its dry run: x")
            ],
            fallback_message="should not be used",
        )
        assert [item.category for item in items] == [ValidationErrorCategory.DRY_RUN]

    def test_fallback_message_suppressed_when_categorized_data_present(self) -> None:
        """A categorized error wins over the fallback residual — the residual is a last resort only."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[
                PipeFactoryErrorData(
                    error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
                    pipe_code="pipe_x",
                    missing_concept_code="Foo",
                    message="concept Foo not found",
                ),
            ],
            pipe_validation_errors=[],
            fallback_message="should not be used",
        )
        assert [item.category for item in items] == [ValidationErrorCategory.PIPE_FACTORY]

    def test_validation_items_are_total_for_message_only_error(self) -> None:
        """A bare-message ``ValidateBundleError`` still lists a non-empty set of items — the invariant is total.

        ``validation_error_items`` passes ``fallback_message=self.message``, so even an error with no
        categorized data and no dry-run channel projects one ``blueprint_validation`` residual, and its
        problem one ``method.schema_violation`` item. An invalid verdict is therefore NEVER a bare
        ``detail`` with no items.
        """
        exc = ValidateBundleError(message="Could not make 'PipelexBundleBlueprint': no blueprint found")
        items = exc.validation_error_items()
        assert [item.category for item in items] == [ValidationErrorCategory.BLUEPRINT_VALIDATION]
        assert items[0].message == "Could not make 'PipelexBundleBlueprint': no blueprint found"
        problem = exc.to_problem(view=ProblemView.CALLER)
        assert problem.errors is not None
        assert [item.code for item in problem.errors] == [CoreCode.METHOD_SCHEMA_VIOLATION]

    def test_empty_collections_collapse_to_none(self) -> None:
        """An empty ``declared_concepts`` / ``variable_names`` becomes ``None`` so it drops from the wire."""
        exc = ValidateBundleError(
            message="validation failed",
            pipe_factory_errors=[
                PipeFactoryErrorData(
                    error_type=PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR,
                    pipe_code="pipe_x",
                    declared_concepts=[],
                    message="boom",
                ),
            ],
        )
        factory_item = _build_items(exc)[0]
        assert factory_item.declared_concepts is None

    def test_the_problem_s_errors_follow_the_builder_s_items_one_for_one(self) -> None:
        """The problem the agent CLI prints lists one fault per item of the API's invalid verdict, at the same pipe.

        The API's verdict is the ``BundleValidationFailure`` a validator returns, built as the direct validator builds
        it; its items are dumped to the wire and compared as encoded JSON, so a field that diverges between Python and
        JSON would show.
        """
        exc = _all_category_error()
        verdict = BundleValidationFailure(problem=exc.to_problem(view=ProblemView.OPERATOR), validation_errors=exc.validation_error_items())
        verdict_items = verdict.model_dump(mode="json", exclude_none=True)["validation_errors"]
        builder_dicts = [item.model_dump(mode="json", exclude_none=True) for item in _build_items(exc)]
        assert json.dumps(verdict_items, sort_keys=True) == json.dumps(builder_dicts, sort_keys=True)

        problem_items = exc.to_problem(view=ProblemView.OPERATOR).errors
        assert problem_items is not None
        assert len(problem_items) == len(builder_dicts)
        assert [item.location.pipe if item.location else None for item in problem_items] == [item.get("pipe_code") for item in builder_dicts]

    def test_enriched_pipe_validation_error_rides_a_suggested_fix(self) -> None:
        """An enriched output-mismatch error data yields an item carrying the planner's suggested_fix."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[
                PipesAndConceptValidationErrorData(
                    error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                    domain_code="testapp",
                    source="main.mthds",
                    pipe_code="list_ideas",
                    message="output mismatch",
                    field_path="",
                    expected_output_ref="Idea[]",
                ),
            ],
        )
        assert len(items) == 1
        suggested_fix = items[0].suggested_fix
        assert suggested_fix is not None
        assert suggested_fix.fix_code == "match-sequence-output"
        assert suggested_fix.ops == [SetKeyOp(table_path=["pipe", "list_ideas"], key="output", value="Idea[]")]

    def test_input_drift_error_rides_a_sync_controller_inputs_fix(self) -> None:
        """An enriched controller input-drift error data yields an item carrying the multi-op fix."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[
                PipesAndConceptValidationErrorData(
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code="testapp",
                    source="main.mthds",
                    pipe_code="make_summary",
                    message="input drift",
                    field_path="",
                    expected_inputs={"text": "Text"},
                    declared_inputs={"text": "Number", "note": "Text"},
                ),
            ],
        )
        assert len(items) == 1
        suggested_fix = items[0].suggested_fix
        assert suggested_fix is not None
        assert suggested_fix.fix_code == "sync-controller-inputs"
        assert suggested_fix.source == "main.mthds"
        inputs_table_path = ["pipe", "make_summary", "inputs"]
        assert suggested_fix.ops == [
            SetKeyOp(table_path=inputs_table_path, key="text", value="Text"),
            DeleteKeyOp(table_path=inputs_table_path, key="note"),
        ]

    def test_blueprint_native_redeclaration_rides_a_strip_fix(self) -> None:
        """An enriched native-concept redeclaration blueprint error carries the strip fix through the builder.

        First blueprint-channel fix: the builder's blueprint loop now runs the planner too, and the
        fix carries a populated ``source`` (blueprint error data has one, unlike the pipe raise sites).
        """
        items = build_validation_error_items(
            blueprint_errors=[
                PipelexBundleBlueprintValidationErrorData(
                    error_type=PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION,
                    domain_code="nativefix",
                    source="main.mthds",
                    concept_code="Text",
                    message="Cannot declare a concept named 'Text' because it is natively available in Pipelex.",
                ),
            ],
            factory_errors=[],
            pipe_validation_errors=[],
        )
        assert len(items) == 1
        suggested_fix = items[0].suggested_fix
        assert suggested_fix is not None
        assert suggested_fix.fix_code == "strip-native-concept-redecl"
        assert suggested_fix.source == "main.mthds"
        assert suggested_fix.ops == [DeleteKeyOp(table_path=["concept"], key="Text")]

    def test_blueprint_strip_namespace_rides_a_rename_fix(self) -> None:
        """An enriched same-domain dotted declaration carries a strip-namespace rename through the builder."""
        items = build_validation_error_items(
            blueprint_errors=[
                PipelexBundleBlueprintValidationErrorData(
                    error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
                    domain_code="greetings",
                    source="main.mthds",
                    pipe_code="greetings.hello",
                    stripped_pipe_code="hello",
                    message="Pipe code 'greetings.hello' is not a valid pipe code. Must be in snake_case.",
                ),
            ],
            factory_errors=[],
            pipe_validation_errors=[],
        )
        assert len(items) == 1
        suggested_fix = items[0].suggested_fix
        assert suggested_fix is not None
        assert suggested_fix.fix_code == "strip-namespace"
        assert suggested_fix.ops == [RenameTableKeyOp(table_path=["pipe"], key="greetings.hello", new_key="hello")]

    def test_non_fixable_blueprint_error_has_no_suggested_fix(self) -> None:
        """An un-enriched INVALID_PIPE_CODE_SYNTAX (no ``stripped_pipe_code``) keeps ``suggested_fix`` unset."""
        items = build_validation_error_items(
            blueprint_errors=[
                PipelexBundleBlueprintValidationErrorData(
                    error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
                    domain_code="nativefix",
                    source="main.mthds",
                    message="Invalid pipe code syntax",
                ),
            ],
            factory_errors=[],
            pipe_validation_errors=[],
        )
        assert len(items) == 1
        assert items[0].suggested_fix is None

    def test_non_fixable_pipe_validation_error_has_no_suggested_fix(self) -> None:
        """A pipe-validation item with no enriched data keeps suggested_fix unset (wire unchanged)."""
        items = _build_items(_all_category_error())
        assert all(item.suggested_fix is None for item in items)
        for item in items:
            assert "suggested_fix" not in item.model_dump(mode="json", exclude_none=True)

    def test_instantiation_errors_are_projected_as_pipe_validation(self) -> None:
        """Pipe/concept *instantiation* errors reach the wire too (not silently dropped).

        ``ValidateBundleError`` aggregates them in a separate list; both real call sites route
        through ``pipe_validation_error_data`` so they project as ``PIPE_VALIDATION`` items.
        """
        exc = ValidateBundleError(
            message="validation failed",
            pipe_concept_instantiation_errors=[
                PipesAndConceptValidationErrorData(
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    source="instantiated.mthds",
                    pipe_code="pipe_inst",
                    message="instantiation failed",
                    field_path="pipe_inst.inputs.z",
                ),
            ],
        )
        items = _build_items(exc)
        assert [item.category for item in items] == [ValidationErrorCategory.PIPE_VALIDATION]
        assert items[0].source == "instantiated.mthds"
        # And the verdict lists it (it would be missing if the list were dropped).
        assert [item.pipe_code for item in exc.validation_error_items()] == ["pipe_inst"]

    def test_warnings_become_problem_items_under_the_code_their_type_names(self) -> None:
        """A valid report's warnings, as a surface speaking problem items carries them: each type names its code, and a
        warning no type classifies takes `method.schema_violation`, as an unclassified item of an invalid verdict does.
        """
        hint_warning = ValidationErrorItem(
            category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
            error_type=HintLintErrorType.HINT_UNKNOWN_KEY,
            concept_code="Essay",
            domain_code="docs",
            hint_key="emphasis",
            message="Hint key 'emphasis' on concept 'docs.Essay' is not defined by this version of the standard.",
        )
        template_warning = ValidationErrorItem(
            category=ValidationErrorCategory.DRY_RUN,
            error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
            pipe_code="print_invoice",
            template_file="invoice.xlsx",
            message="The name Totl matches no field.",
        )
        unclassified_warning = ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="Something to look at.")

        items = warning_problem_items(warnings=[hint_warning, template_warning, unclassified_warning])

        assert [item.model_dump(mode="json", exclude_none=True) for item in items] == [
            {
                "code": "method.hint_invalid",
                "detail": items[0].detail,
                "params": {"reason": "unknown_key", "hint": "emphasis"},
                # The declaration the hint is on, which neither parameter names.
                "location": {"field": "concept.Essay"},
            },
            {
                "code": "pipelex.docgen.template_warning",
                "detail": "The document template 'invoice.xlsx' may be faulty: The name Totl matches no field.",
                "params": {"template": "invoice.xlsx", "finding": "The name Totl matches no field."},
                "location": {"pipe": "print_invoice"},
            },
            {
                "code": "method.schema_violation",
                "detail": items[2].detail,
                "params": {"finding": "Something to look at."},
            },
        ]
        assert "emphasis" in items[0].detail
