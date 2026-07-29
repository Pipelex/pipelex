"""Unit tests for ``build_validation_error_items`` — the shared structured-error builder.

The single builder feeds both the agent CLI's ``validation_errors`` JSON array
(via ``extract_validation_errors``) and the API 422's
``ErrorReport.validation_errors`` (via ``ValidateBundleError.to_error_report``),
so the two surfaces can never drift. These tests pin the per-category field
projection — including the ``source`` / ``field_name`` / ``concept_code`` fields
that the older CLI-only extractor dropped — and the CLI↔API shape parity.
"""

import json

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import extract_validation_errors
from pipelex.core.exceptions import PipeFactoryErrorData, PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validation_errors import build_validation_error_items
from pipelex.suggested_fix import FixOpKind


def _build_items(exc: ValidateBundleError) -> list[ValidationErrorItem]:
    """Call the builder with the error's categorized lists only — for the category-projection tests.

    The pipe-validation arm uses ``pipe_validation_error_data`` (pipe validation **plus**
    pipe/concept instantiation errors) — the same combined accessor both real call sites
    (``ValidateBundleError.to_error_report`` and the CLI ``extract_validation_errors``) pass.
    The residual channels (``dry_run_error_message`` / ``fallback_message``) are intentionally
    omitted here so these tests pin the categorized projection in isolation; the residual behavior
    has its own dedicated tests below.
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

    def test_dry_run_residual_becomes_single_dry_run_item(self) -> None:
        """A residual dry-run failure (no categorized data) yields one ``dry_run`` item — the structured-info invariant.

        This is the case that previously produced a bare-message error with an empty
        ``validation_errors[]``; it now carries the message as a ``dry_run``-category item.
        It is graph-level, so it has no ``source``.
        """
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[],
            dry_run_error_message="Dry run failed: residual error",
        )
        assert [item.category for item in items] == [ValidationErrorCategory.DRY_RUN]
        assert items[0].message == "Dry run failed: residual error"
        assert items[0].error_type == "DryRunError"
        assert items[0].source is None

    def test_dry_run_residual_suppressed_when_categorized_data_present(self) -> None:
        """When a categorized error carries data, the dry-run residual is NOT added — the categorized items win."""
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
            dry_run_error_message="should be ignored",
        )
        assert [item.category for item in items] == [ValidationErrorCategory.PIPE_FACTORY]

    def test_to_error_report_projects_dry_run_residual(self) -> None:
        """A ``ValidateBundleError`` carrying only ``dry_run_error_message`` surfaces one ``dry_run`` item on the report."""
        report = ValidateBundleError(message="Dry run failed", dry_run_error_message="Dry run failed: residual error").to_error_report()
        assert report.validation_errors is not None
        assert [item.category for item in report.validation_errors] == [ValidationErrorCategory.DRY_RUN]

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

    def test_dry_run_residual_wins_over_fallback_message(self) -> None:
        """When both residual channels are available, the more-specific ``dry_run`` item wins (ordering)."""
        items = build_validation_error_items(
            blueprint_errors=[],
            factory_errors=[],
            pipe_validation_errors=[],
            dry_run_error_message="Dry run failed: residual error",
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

    def test_to_error_report_is_total_for_message_only_error(self) -> None:
        """A bare-message ``ValidateBundleError`` still surfaces a non-empty ``validation_errors`` — the invariant is total.

        ``to_error_report`` passes ``fallback_message=self.message``, so even an error with no
        categorized data and no dry-run channel projects one ``blueprint_validation`` residual.
        An invalid verdict is therefore NEVER a bare ``detail`` with an empty ``validation_errors[]``.
        """
        report = ValidateBundleError(message="Could not make 'PipelexBundleBlueprint': no blueprint found").to_error_report()
        assert report.validation_errors is not None
        assert report.validation_errors  # non-empty: the totality guarantee
        assert [item.category for item in report.validation_errors] == [ValidationErrorCategory.BLUEPRINT_VALIDATION]
        assert report.validation_errors[0].message == "Could not make 'PipelexBundleBlueprint': no blueprint found"

    def test_cli_extractor_is_total_for_message_only_error(self) -> None:
        """The CLI ``extract_validation_errors`` is also total — a bare-message error yields one item, never an empty array."""
        cli_dicts = extract_validation_errors(ValidateBundleError(message="empty blueprint"))
        assert cli_dicts == [{"category": "blueprint_validation", "message": "empty blueprint"}]

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

    def test_cli_extractor_matches_builder_dumped_shape(self) -> None:
        """The CLI ``extract_validation_errors`` dicts equal the dumped builder items — single shape, two surfaces.

        Pins that the agent CLI and the API 422 emit the identical structured
        items: the CLI adapter is exactly ``model_dump(exclude_none=True)`` over
        the same builder the API report uses.
        """
        exc = _all_category_error()
        cli_dicts = extract_validation_errors(exc)
        builder_dicts = [item.model_dump(mode="json", exclude_none=True) for item in _build_items(exc)]
        assert cli_dicts == builder_dicts

    def test_cli_extractor_equals_api_report_validation_errors(self) -> None:
        """The CLI array and the API 422 ``validation_errors`` are identical on the wire.

        The API report path dumps in python mode (``to_dict`` → ``model_dump(exclude_none=True)``),
        so ``category`` rides as a live ``ValidationErrorCategory`` enum, while the CLI dumps
        ``mode="json"`` strings. A plain ``==`` would pass merely because ``StrEnum`` subclasses
        ``str``; to prove *wire-byte* parity (and catch a future python/json-divergent field that
        is not a StrEnum), we also compare the encoded JSON, not just the in-memory dicts.
        """
        exc = _all_category_error()
        cli_dicts = extract_validation_errors(exc)
        problem_document = exc.to_error_report().to_problem_document()
        assert problem_document["validation_errors"] == cli_dicts
        assert json.dumps(problem_document["validation_errors"], sort_keys=True) == json.dumps(cli_dicts, sort_keys=True)

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
        assert suggested_fix.ops[0].table_path == ["pipe", "list_ideas"]
        assert suggested_fix.ops[0].value == "Idea[]"

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
        assert [(op.kind, op.key) for op in suggested_fix.ops] == [
            (FixOpKind.SET_KEY, "text"),
            (FixOpKind.DELETE_KEY, "note"),
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
        assert [(op.kind, op.table_path, op.key) for op in suggested_fix.ops] == [(FixOpKind.DELETE_KEY, ["concept"], "Text")]

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
        assert [(op.kind, op.table_path, op.key, op.new_key) for op in suggested_fix.ops] == [
            (FixOpKind.RENAME_TABLE_KEY, ["pipe"], "greetings.hello", "hello"),
        ]

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
        # And the API report surfaces it (would be None/empty if the list were dropped).
        report = exc.to_error_report()
        assert report.validation_errors is not None
        assert report.validation_errors[0].pipe_code == "pipe_inst"
