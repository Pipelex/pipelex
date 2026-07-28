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
from pipelex.core.exceptions import PipeFactoryErrorData, PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.pipeline.fixes.planner import plan_fix_for_blueprint_validation_error, plan_fix_for_pipe_validation_error


def build_validation_error_items(
    *,
    blueprint_errors: list[PipelexBundleBlueprintValidationErrorData],
    factory_errors: list[PipeFactoryErrorData],
    pipe_validation_errors: list[PipesAndConceptValidationErrorData],
    dry_run_error_message: str | None = None,
    fallback_message: str | None = None,
) -> list[ValidationErrorItem]:
    """Flatten a bundle-validation error's categorized lists into typed items.

    Covers the three populated error-data sources a ``ValidateBundleError``
    aggregates — blueprint validation, pipe-factory, and pipe/concept validation
    — tagging each item with its :class:`ValidationErrorCategory`. Empty
    collections collapse to ``None`` so they drop out of the ``exclude_none``
    wire projection. The ``source`` (declaring file path) rides whenever the
    underlying error-data model carries it, so a consumer can map each error to
    its owning file.

    Two residual safety nets make the structured-info invariant **total** — an
    invalid verdict never rides a bare ``detail`` with an empty
    ``validation_errors[]``:

    - The ``dry_run`` residual: a dry-run failure (``DryRunError`` /
      ``PipeRunError``) surfaces only a single message, not per-error data with
      identity fields. When it is the *only* failure channel (no categorized
      error has data), it becomes one :class:`ValidationErrorCategory.DRY_RUN`
      item carrying that message.
    - The ``fallback_message`` residual: a parse-level failure (a TOML-syntax
      error, an empty blueprint, a bundle-elaborator failure) surfaces only the
      error's top-level message, with no categorized data and no dry-run channel.
      When *nothing else* produced an item, it becomes one
      :class:`ValidationErrorCategory.BLUEPRINT_VALIDATION` item carrying that
      message — the bundle could not be turned into a blueprint at all.

    Both residuals are graph/parse-level (the builder has no file context), so
    they carry no ``source``. They are ordered ``dry_run`` then
    ``fallback_message`` (most-specific channel first): a dry-run failure that
    also passes a fallback message must still surface its ``dry_run`` item, and
    the ``not items`` guard on each block guarantees only one residual fires.

    Args:
        blueprint_errors: Interpreter / blueprint-validation error data.
        factory_errors: Pipe-factory error data (e.g. a missing concept).
        pipe_validation_errors: Pipe/concept validation error data.
        dry_run_error_message: The residual dry-run failure message, if any. Only
            projected as a ``dry_run`` item when no categorized error has data.
        fallback_message: The error's caller-facing message, used as the
            last-resort residual. Only projected as a ``blueprint_validation``
            item when no categorized error and no dry-run residual produced one.

    Returns:
        One :class:`ValidationErrorItem` per underlying error, in the order
        blueprint → factory → pipe/concept validation, then the ``dry_run`` or
        (last-resort) ``fallback_message`` residual when it is the sole failure
        channel.
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
                message=pipe_error.message,
                suggested_fix=plan_fix_for_pipe_validation_error(pipe_error),
            )
        )

    # The dry-run residual is the structured-info safety net: emit it only when no categorized
    # error carries data, so an invalid verdict driven solely by a dry-run failure still surfaces
    # a non-empty validation_errors[] instead of a bare detail. Graph-level → no source.
    if not items and dry_run_error_message:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.DRY_RUN,
                error_type="DryRunError",
                message=dry_run_error_message,
            )
        )

    # Last-resort residual: a parse-level failure (TOML syntax, an empty blueprint, a bundle
    # elaborator failure) surfaces only a top-level message — no categorized data and no dry-run
    # channel. Emit one BLUEPRINT_VALIDATION item carrying that message so an invalid verdict is
    # NEVER a bare detail with an empty validation_errors[] — the structured-info invariant, now
    # total. The bundle could not be turned into a blueprint at all, so blueprint_validation is the
    # right bucket; parse-level → no source, and error_type stays None (the message is
    # authoritative and the residual fires for several distinct underlying errors). Ordered after
    # the dry_run residual (the more specific channel); the `not items` guard fires only one.
    if not items and fallback_message:
        items.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
                message=fallback_message,
            )
        )

    return items
