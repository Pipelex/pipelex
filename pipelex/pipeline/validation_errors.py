"""Shared builder that flattens bundle-validation error data into typed wire items, and those into problem items.

``build_validation_error_items`` is the single source of truth behind every
structured-error surface:

- the ``/validate`` route's invalid verdict,
- the problem's ``errors`` (via ``ValidateBundleError.problem_items``, which
  turns each item into a problem item with :func:`problem_item_of`), which the
  agent CLI prints, and
- the agent CLI's Markdown, which renders the items themselves as prose.

A valid report's advisory ``warnings`` are the same items, and :func:`warning_problem_items` turns them into problem
items for a surface that speaks problem items, such as the runner's ``/validate``.

All of them reach it through ``ValidateBundleError.validation_error_items``, so the CLI
and API structured shapes cannot drift. It takes the error-data lists directly
rather than a ``ValidateBundleError`` instance — that keeps the dependency one-directional
(``pipelex.pipeline.exceptions`` imports this module, never the reverse) so there
is no import cycle.
"""

from typing import Any

from mthds.protocol.problem.models import ProblemItem, ProblemLocation
from mthds.protocol.problem.registry import (
    CoreCode,
    MethodDependencyMissingKind,
    MethodDependencyMissingReason,
    MethodHintInvalidReason,
    MethodIdentifierInvalidIdentifierKind,
    MethodNameConflictConflict,
)
from pydantic import BaseModel, ConfigDict

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.core.pipes.exceptions import pipe_validation_error_code
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.problem import make_location, make_problem_item
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipeline.fixes.planner import plan_fix_for_blueprint_validation_error, plan_fix_for_pipe_validation_error
from pipelex.tools.misc.string_utils import close_matches
from pipelex.validation_error_types import (
    HintLintErrorType,
    PipeFactoryErrorType,
    PipeValidationErrorType,
    TemplateCheckErrorType,
    ValidationResidualErrorType,
)


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
        fallback_message: The error's message, used as the
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
                field_name=blueprint_error.field_name,
                variable_names=blueprint_error.variable_names or None,
                declared_concepts=blueprint_error.declared_concepts or None,
                identifier_name=blueprint_error.identifier_name,
                params=blueprint_error.params,
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
                params=pipe_error.params,
                message=pipe_error.message,
                suggested_fix=plan_fix_for_pipe_validation_error(pipe_error),
            )
        )

    # One located item per failing pipe: the sweep already reduced a failure that made enclosing
    # controllers fail to the innermost pipe, and gave each failure the sentence its code renders for a caller.
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


class ValidationItemCode(BaseModel):
    """The code a validation item takes in its verdict's problem, with the parameters known beside the item that it renders from.

    A verdict decides it (``ValidateBundleError.item_codes``) from more than the item holds, the refusal it was built from and
    its dry-run failures, so a surface that reports the items after the verdict is gone, ``fix bundle``'s, keeps it beside them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode
    params: dict[str, Any] | None = None


def validation_item_code(*, item: ValidationErrorItem, residual_code: ErrorCode) -> ErrorCode:
    """The code of a validation item that is not a dry run's: its ``error_type``'s, or ``residual_code`` for an item with none.

    Args:
        item: The item.
        residual_code: The code of the refusal the verdict was built from, which an item no stage classified takes.

    Returns:
        The item's code.
    """
    error_type = item.error_type
    if error_type is None:
        return residual_code
    if isinstance(error_type, PipeValidationErrorType):
        return pipe_validation_error_code(error_type=error_type)
    if isinstance(error_type, PipeFactoryErrorType):
        match error_type:
            case PipeFactoryErrorType.UNKNOWN_CONCEPT:
                return CoreCode.METHOD_CONCEPT_UNRESOLVED
            case PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR:
                return CoreCode.METHOD_SCHEMA_VIOLATION
    if isinstance(error_type, HintLintErrorType):
        return CoreCode.METHOD_HINT_INVALID
    if isinstance(error_type, TemplateCheckErrorType):
        return PipelexErrorCode.DOCGEN_TEMPLATE_WARNING
    # The dry-run residual, whose items take their failure's own code.
    return residual_code


def _hint_reason(*, error_type: HintLintErrorType) -> MethodHintInvalidReason:
    """The `reason` of `method.hint_invalid` a hint lint finding of this type gives."""
    match error_type:
        case HintLintErrorType.HINT_UNKNOWN_KEY:
            return MethodHintInvalidReason.UNKNOWN_KEY
        case HintLintErrorType.HINT_UNKNOWN_INTENT:
            return MethodHintInvalidReason.UNKNOWN_INTENT
        case HintLintErrorType.HINT_INAPPLICABLE_INTENT:
            return MethodHintInvalidReason.INAPPLICABLE_INTENT


def _hint_facts(*, item: ValidationErrorItem) -> dict[str, Any]:
    """The hint a hint lint item is about and why it is not understood, when the item is one."""
    if not isinstance(item.error_type, HintLintErrorType):
        return {}
    return {"reason": _hint_reason(error_type=item.error_type), "hint": item.hint_key}


def warning_problem_items(*, warnings: list[ValidationErrorItem]) -> list[ProblemItem]:
    """A valid report's advisory warnings as problem items, each with its type's code.

    A warning's type names its code (:func:`validation_item_code`): an advisory pipe lint its own, a hint lint
    `method.hint_invalid`, a template check's finding `pipelex.docgen.template_warning`. A warning no type classifies
    takes `method.schema_violation`, as an unclassified item of an invalid verdict does.

    Args:
        warnings: The report's warnings.

    Returns:
        One problem item per warning, in order.
    """
    return [
        problem_item_of(item=warning, code=validation_item_code(item=warning, residual_code=CoreCode.METHOD_SCHEMA_VIOLATION)) for warning in warnings
    ]


# The identifier an item of these types is about, and where the item holds it: an input name among its variable names, a pipe
# code as its identifier name, else as its pipe. A pipe code item whose field path is `main_pipe` is about the main pipe.
_IDENTIFIER_KINDS: dict[PipeValidationErrorType, MethodIdentifierInvalidIdentifierKind] = {
    PipeValidationErrorType.INVALID_INPUT_NAME: MethodIdentifierInvalidIdentifierKind.INPUT_NAME,
    PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX: MethodIdentifierInvalidIdentifierKind.PIPE_CODE,
}
_MAIN_PIPE_FIELD_PATH = "main_pipe"


def _identifier_facts(*, item: ValidationErrorItem) -> dict[str, Any]:
    """The name an identifier item is about and what the name is, when the item holds the name."""
    if not isinstance(item.error_type, PipeValidationErrorType):
        return {}
    identifier_kind = _IDENTIFIER_KINDS.get(item.error_type)
    if identifier_kind is None:
        return {}
    if identifier_kind == MethodIdentifierInvalidIdentifierKind.PIPE_CODE and item.field_path == _MAIN_PIPE_FIELD_PATH:
        identifier_kind = MethodIdentifierInvalidIdentifierKind.MAIN_PIPE
    match identifier_kind:
        case MethodIdentifierInvalidIdentifierKind.INPUT_NAME:
            name = item.identifier_name or (item.variable_names[0] if item.variable_names else None)
        case MethodIdentifierInvalidIdentifierKind.PIPE_CODE | MethodIdentifierInvalidIdentifierKind.MAIN_PIPE:
            name = item.identifier_name or item.pipe_code
    if name is None:
        return {}
    return {"identifier_kind": identifier_kind, "name": name}


def _dependency_facts(*, item: ValidationErrorItem) -> dict[str, Any]:
    """The package an unresolved package reference names, the prefix of its ``->`` reference, as a missing dependency."""
    if item.error_type not in _PACKAGE_DEPENDENCY_TYPES or not item.missing_pipe_code:
        return {}
    package = QualifiedRef.package_named_by(raw=item.missing_pipe_code)
    return {
        "kind": MethodDependencyMissingKind.PACKAGE,
        "name": package,
        "reason": MethodDependencyMissingReason.NOT_FOUND,
        "package": package,
    }


# The item types about a package the method depends on that could not be resolved.
_PACKAGE_DEPENDENCY_TYPES: frozenset[PipeValidationErrorType] = frozenset({PipeValidationErrorType.UNRESOLVED_PACKAGE_DEPENDENCY})


# How near a declared concept must be to an unresolved one to be offered in its place, as difflib's similarity ratio,
# and how many are offered.
_CLOSE_CONCEPT_CUTOFF = 0.6
_CLOSE_CONCEPT_MAX_MATCHES = 5


def _concept_suggestions(*, item: ValidationErrorItem) -> list[str] | None:
    """The concepts the bundle declares nearest the one an unresolved-concept item names, nearest first; ``None`` for another item."""
    is_unresolved_concept = item.error_type in {PipeValidationErrorType.UNRESOLVED_CONCEPT, PipeFactoryErrorType.UNKNOWN_CONCEPT}
    # A concept-owned reference locates the concept that holds it and names the one it misses in its own parameters.
    concept = (item.params or {}).get("concept") or item.missing_concept_code or item.concept_code
    if not is_unresolved_concept or concept is None:
        return None
    local_code = concept.rsplit(".", 1)[-1]
    return close_matches(
        name=local_code, candidates=item.declared_concepts or [], cutoff=_CLOSE_CONCEPT_CUTOFF, max_matches=_CLOSE_CONCEPT_MAX_MATCHES
    )


# What the name of a `method.name_conflict` item collides with, by the type of the item; a name declared twice across a
# method's bundles is an item no type classifies, which takes the refusal's own parameters.
_NAME_CONFLICTS: dict[PipeValidationErrorType, MethodNameConflictConflict] = {
    PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION: MethodNameConflictConflict.NATIVE_CONCEPT,
    PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION: MethodNameConflictConflict.BATCH_ITEM,
}


# The name conflicts no declaration makes: a batch item named as its list or as another input of its pipe is a name that
# pipe uses twice, located on the pipe and on the field it collides on, as any other item about a pipe is.
_PIPE_NAME_CONFLICTS: frozenset[PipeValidationErrorType] = frozenset({PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION})


def _name_conflict_facts(*, item: ValidationErrorItem) -> dict[str, Any]:
    """The name and the conflict of a name-conflict item: the concept a bundle redeclares, or the batch item's name."""
    conflict = _NAME_CONFLICTS.get(item.error_type) if isinstance(item.error_type, PipeValidationErrorType) else None
    if conflict is None:
        return {}
    name: str | None
    match conflict:
        case MethodNameConflictConflict.NATIVE_CONCEPT:
            name = item.concept_code
        case MethodNameConflictConflict.BATCH_ITEM:
            name = item.variable_names[0] if item.variable_names else None
        case MethodNameConflictConflict.DUPLICATE_DECLARATION | MethodNameConflictConflict.RESERVED_DOMAIN:
            name = None
    return {"name": name, "conflict": conflict}


def _item_facts(*, item: ValidationErrorItem) -> dict[str, Any]:
    """The facts a validation item holds, by the names the registry gives the parameters that carry them."""
    facts: dict[str, Any] = {
        **_identifier_facts(item=item),
        **_dependency_facts(item=item),
        **_hint_facts(item=item),
        **_name_conflict_facts(item=item),
        "template": item.template_file,
        "pipe": item.pipe_code,
        "concept": item.missing_concept_code or item.concept_code,
        "variables": item.variable_names,
        # The one input an item names, for a code about a single input.
        "input": item.variable_names[0] if item.variable_names and len(item.variable_names) == 1 else None,
        "model": item.model_reference,
        "model_type": item.model_type,
        "suggestions": item.suggestions if item.suggestions is not None else _concept_suggestions(item=item),
        "field_path": item.field_path or _declaration_path(item=item),
        "missing": item.missing_pipe_code,
        "finding": item.message,
    }
    return {name: value for name, value in facts.items() if value is not None}


def _declaration_path(*, item: ValidationErrorItem) -> str | None:
    """The bundle-root dot path of the declaration an item is about when it names no field path: its pipe's, or its concept's."""
    if item.pipe_code is not None:
        return f"pipe.{item.pipe_code}.{item.field_name}" if item.field_name else f"pipe.{item.pipe_code}"
    if item.concept_code is not None:
        return f"concept.{item.concept_code}"
    return None


def problem_item_of(*, item: ValidationErrorItem, code: ErrorCode, params: dict[str, Any] | None = None) -> ProblemItem:
    """The problem item of a validation item: its code, the parameters its locators give that code, and its location.

    Args:
        item: The validation item.
        code: Its code: :func:`validation_item_code`'s, or the dry-run failure's own.
        params: Parameters known beside the item, such as those a dry-run failure was rendered from or those of the
            refusal an unclassified item takes its code from, which take precedence over the facts its locators give;
            the parameters the item itself holds (``item.params``) take precedence over both.

    Returns:
        The problem item, its sentence rendered from the code's template.
    """
    spec = error_code_spec(code)
    facts = {**_item_facts(item=item), **(params or {}), **(item.params or {})}
    item_params = {name: value for name, value in facts.items() if name in spec.param_names}
    if "suggestions" in spec.required_params:
        # A stage that offers close matches leaves the list out when it found none, which the code reads as an empty one.
        item_params.setdefault("suggestions", [])
    return make_problem_item(
        code=code,
        params=item_params,
        location=_item_location(item=item, code=code),
        suggestions=item.suggestions,
        suggested_fix=_problem_fix(item=item),
    )


def _item_location(*, item: ValidationErrorItem, code: ErrorCode) -> ProblemLocation | None:
    """Where in the method a validation item is: the declaration a hint lint is on, the declaration a name conflict
    collides on, else the pipe, field and file it names.
    """
    if isinstance(item.error_type, HintLintErrorType):
        return _hint_location(item=item)
    line = item.line if item.line is not None and item.line >= 1 else None
    column = item.column if item.column is not None and item.column >= 1 else None
    if code == CoreCode.METHOD_NAME_CONFLICT and item.error_type not in _PIPE_NAME_CONFLICTS:
        # A declaration's name conflict, a duplicate declaration or a native concept's redeclaration, is located on the
        # declaration that collides, by its path from the bundle's root, such as `concept.Rating` or `pipe.compute_score`,
        # which a caller edits. A `field` beside no `pipe` reads from the bundle's root, so the location names no `pipe` a
        # reader would join that path to.
        return make_location(field=item.field_path or _declaration_path(item=item), file=item.source, line=line, column=column)
    return make_location(pipe=item.pipe_code, field=item.field_name or item.field_path or None, file=item.source, line=line, column=column)


def _hint_location(*, item: ValidationErrorItem) -> ProblemLocation | None:
    """The declaration a hint lint finding is on, which neither of `method.hint_invalid`'s parameters names.

    A hint sits on one of three sites (`pipelex.pipeline.hint_warnings`): an input of a pipe, located at the pipe and the
    input; a concept, located at its bundle-root path, `concept.<Concept>`; a field of a concept's structure, at the
    field's, `concept.<Concept>.structure.<field>`. The domain is not part of the path, as no item's is: a bundle-root
    path is read in the bundle that declares the concept.
    """
    if item.pipe_code is not None:
        input_name = item.variable_names[0] if item.variable_names else None
        return make_location(pipe=item.pipe_code, input_name=input_name)
    if item.concept_code is not None:
        concept_path = f"concept.{item.concept_code}"
        return make_location(field=f"{concept_path}.structure.{item.field_name}" if item.field_name else concept_path)
    return None


def _problem_fix(*, item: ValidationErrorItem) -> dict[str, Any] | None:
    """An item's suggested fix in the standard's wire form, where the file it edits is ``file``, not ``source``."""
    if item.suggested_fix is None:
        return None
    fix = item.suggested_fix.model_dump(mode="json", exclude_none=True)
    source = fix.pop("source", None)
    if source is not None:
        fix["file"] = source
    return fix
