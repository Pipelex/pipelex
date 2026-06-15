"""Shared builder that flattens bundle-validation error data into typed wire items.

``build_validation_error_items`` is the single source of truth behind both
structured-error surfaces:

- the agent CLI's ``validation_errors`` JSON array (via
  ``pipelex.cli.agent_cli.commands.agent_output.extract_validation_errors``), and
- the API 422's ``ErrorReport.validation_errors`` (via
  ``ValidateBundleError.to_error_report``).

Both call this one builder, so the CLI and API structured shapes cannot drift.
It takes the three categorized error-data lists directly rather than a
``ValidateBundleError`` instance — that keeps the dependency one-directional
(``pipelex.pipeline.exceptions`` imports this module, never the reverse) so there
is no import cycle.
"""

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData


def build_validation_error_items(
    *,
    blueprint_errors: list[PipelexBundleBlueprintValidationErrorData],
    factory_errors: list[PipeFactoryErrorData],
    pipe_validation_errors: list[PipesAndConceptValidationErrorData],
) -> list[ValidationErrorItem]:
    """Flatten a bundle-validation error's categorized lists into typed items.

    Covers the three populated error-data sources a ``ValidateBundleError``
    aggregates — blueprint validation, pipe-factory, and pipe/concept validation
    — tagging each item with its :class:`ValidationErrorCategory`. Empty
    collections collapse to ``None`` so they drop out of the ``exclude_none``
    wire projection. The ``source`` (declaring file path) rides whenever the
    underlying error-data model carries it, so a consumer can map each error to
    its owning file.

    Args:
        blueprint_errors: Interpreter / blueprint-validation error data.
        factory_errors: Pipe-factory error data (e.g. a missing concept).
        pipe_validation_errors: Pipe/concept validation error data.

    Returns:
        One :class:`ValidationErrorItem` per underlying error, in the order
        blueprint → factory → pipe/concept validation.
    """
    items: list[ValidationErrorItem] = []

    for blueprint_error in blueprint_errors:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
                error_type=blueprint_error.error_type,
                pipe_code=blueprint_error.pipe_code,
                concept_code=blueprint_error.concept_code,
                domain_code=blueprint_error.domain_code,
                source=blueprint_error.source,
                variable_names=blueprint_error.variable_names or None,
                message=blueprint_error.message,
            )
        )

    for factory_error in factory_errors:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.PIPE_FACTORY,
                error_type=factory_error.error_type,
                pipe_code=factory_error.pipe_code,
                domain_code=factory_error.domain_code,
                missing_concept_code=factory_error.missing_concept_code,
                declared_concepts=factory_error.declared_concepts or None,
                message=factory_error.message,
            )
        )

    for pipe_error in pipe_validation_errors:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.PIPE_VALIDATION,
                error_type=pipe_error.error_type,
                pipe_code=pipe_error.pipe_code,
                concept_code=pipe_error.concept_code,
                domain_code=pipe_error.domain_code,
                source=pipe_error.source,
                field_path=pipe_error.field_path or None,
                field_name=pipe_error.field_name,
                variable_names=pipe_error.variable_names or None,
                message=pipe_error.message,
            )
        )

    return items
