"""Shared builder that flattens bundle-validation error data into typed wire items.

``build_validation_error_items`` is the single source of truth behind both
structured-error surfaces:

- the agent CLI's ``validation_errors`` JSON array (via
  ``pipelex.cli.agent_cli.commands.agent_output.extract_validation_errors``), and
- the API report's ``ErrorReport.validation_errors`` (via
  ``ValidateBundleError.to_error_report``).

Both reach it through ``ValidateBundleError.validation_error_items``, so the CLI
and API structured shapes cannot drift. It takes the error-data lists directly
rather than a ``ValidateBundleError`` instance — that keeps the dependency one-directional
(``pipelex.pipeline.exceptions`` imports this module, never the reverse) so there
is no import cycle.
"""

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.pipeline.fixes.planner import plan_fix_for_blueprint_validation_error, plan_fix_for_pipe_validation_error
from pipelex.validation_error_types import ValidationResidualErrorType


def build_validation_error_items(
    *,
    blueprint_errors: list[PipelexBundleBlueprintValidationErrorData],
    factory_errors: list[PipeFactoryErrorData],
    pipe_validation_errors: list[PipesAndConceptValidationErrorData],
    dry_run_failures: list[DryRunFailureErrorData] | None = None,
    fallback_message: str | None = None,
) -> list[ValidationErrorItem]:
    """Flatten a bundle-validation error's categorized lists into typed items.

    Covers the four error-data sources a ``ValidateBundleError`` aggregates —
    blueprint validation, pipe-factory, pipe/concept validation and the dry-run
    failures — tagging each item with its :class:`ValidationErrorCategory`. Empty
    collections collapse to ``None`` so they drop out of the ``exclude_none``
    wire projection. The ``source`` (declaring file path) rides whenever the
    underlying error-data model carries it, so a consumer can map each error to
    its owning file.

    Every dry-run failure becomes its own :class:`ValidationErrorCategory.DRY_RUN`
    item, located at the pipe whose dry run failed (its ``pipe_code``,
    ``domain_code`` and ``source``), with the ``DryRunError`` code the dry-run
    items have always carried.

    One residual safety net makes the structured-info invariant **total** — an
    invalid verdict never rides a bare ``detail`` with an empty
    ``validation_errors[]``: a parse-level failure that surfaces only the error's
    top-level message (an empty blueprint, a bundle-elaborator failure) becomes,
    when *nothing else* produced an item, one
    :class:`ValidationErrorCategory.BLUEPRINT_VALIDATION` item carrying
    ``fallback_message``, with no ``source`` since the builder has no file context.

    Args:
        blueprint_errors: Interpreter / blueprint-validation error data.
        factory_errors: Pipe-factory error data (e.g. a missing concept).
        pipe_validation_errors: Pipe/concept validation error data.
        dry_run_failures: One located failure per pipe whose dry run failed.
        fallback_message: The error's caller-facing message, used as the
            last-resort residual. Only projected as a ``blueprint_validation``
            item when no other channel produced one.

    Returns:
        One :class:`ValidationErrorItem` per underlying error, in the order
        blueprint → factory → pipe/concept validation → dry run, then the
        (last-resort) ``fallback_message`` residual when nothing else produced one.
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
                field_path=blueprint_error.field_path,
                variable_names=blueprint_error.variable_names or None,
                declared_concepts=blueprint_error.declared_concepts or None,
                line=blueprint_error.line,
                column=blueprint_error.column,
                message=blueprint_error.message,
                suggested_fix=plan_fix_for_blueprint_validation_error(blueprint_error),
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
                missing_pipe_code=pipe_error.missing_pipe_code,
                domain_code=pipe_error.domain_code,
                source=pipe_error.source,
                field_path=pipe_error.field_path or None,
                field_name=pipe_error.field_name,
                variable_names=pipe_error.variable_names or None,
                declared_concepts=pipe_error.declared_concepts or None,
                model_reference=pipe_error.model_reference,
                model_type=pipe_error.model_type,
                suggestions=pipe_error.suggestions or None,
                message=pipe_error.message,
                suggested_fix=plan_fix_for_pipe_validation_error(pipe_error),
            )
        )

    # One located item per failing pipe: the sweep already reduced a failure that made enclosing
    # controllers fail to the innermost pipe, and built each message under the disclosure rule.
    for dry_run_failure in dry_run_failures or []:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.DRY_RUN,
                error_type=ValidationResidualErrorType.DRY_RUN_ERROR,
                pipe_code=dry_run_failure.pipe_code,
                domain_code=dry_run_failure.domain_code,
                source=dry_run_failure.source,
                message=dry_run_failure.message,
            )
        )

    # Last-resort residual: a parse-level failure (an empty blueprint, a bundle elaborator failure)
    # surfaces only a top-level message — no categorized data and no dry-run channel. Emit one
    # BLUEPRINT_VALIDATION item carrying that message so an invalid verdict is NEVER a bare detail
    # with an empty validation_errors[] — the structured-info invariant, now total. The bundle could
    # not be turned into a blueprint at all, so blueprint_validation is the right bucket; parse-level
    # → no source, and error_type stays None (the message is authoritative and the residual fires for
    # several distinct underlying errors).
    if not items and fallback_message:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
                message=fallback_message,
            )
        )

    return items
