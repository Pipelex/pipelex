"""Unit tests for ``build_validation_error_items`` — the shared structured-error builder.

The single builder feeds both the agent CLI's ``validation_errors`` JSON array
(via ``extract_validation_errors``) and the API 422's
``ErrorReport.validation_errors`` (via ``ValidateBundleError.to_error_report``),
so the two surfaces can never drift. These tests pin the per-category field
projection — including the ``source`` / ``field_name`` / ``concept_code`` fields
that the older CLI-only extractor dropped — and the CLI↔API shape parity.
"""

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import extract_validation_errors
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validation_errors import build_validation_error_items


def _build_items(exc: ValidateBundleError) -> list[ValidationErrorItem]:
    """Call the builder with the error's three categorized lists (its real call shape)."""
    return build_validation_error_items(
        blueprint_errors=exc.pipelex_bundle_blueprint_validation_errors,
        factory_errors=exc.pipe_factory_errors,
        pipe_validation_errors=exc.pipe_validation_errors,
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
        """The CLI dicts deep-equal the API report's ``validation_errors`` — cross-surface parity."""
        exc = _all_category_error()
        cli_dicts = extract_validation_errors(exc)
        problem_document = exc.to_error_report().to_problem_document()
        # StrEnum ``category`` compares equal to its string value, so the dicts match regardless
        # of dump mode (the API report dumps in python mode, the CLI in json mode).
        assert problem_document["validation_errors"] == cli_dicts
