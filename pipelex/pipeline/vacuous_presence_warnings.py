"""The vacuous-presence lint (`input_presence_vacuous`) for the validate surfaces.

A method input declared without `?` says "the caller must supply this". When the concept behind
that input declares no required field, the concept's schema admits `{}` — so the only thing the
declaration can enforce is that the caller supplies an empty object. Nothing is actually demanded,
and every consumer that has to *materialise* the input (a form, an API client, a human) is left
inventing a meaning. That is what this lint names, on the report's advisory `warnings` array, so it
never flips `is_valid`.

Two scoping decisions define the rule, both stated in `wip/full-optional/design.md`:

- **Entry pipes only.** The smell exists at the boundary where a caller has to conjure the value —
  the bundle's declared `main_pipe`. On an inner pipe the slot is fed by dataflow, and an
  all-optional structure is a legitimate and common producer shape ("record whatever the document
  states"), so neither remedy the message offers would apply.
- **Judged on `gating`, not on `presence`.** `gating` is the descriptor's stated fact that a
  renderer must block Run until the slot has content, and the lint is precisely "you asked for a
  gate but content is undefinable here". Keying the lint on the same fact the renderer keys on
  means the two cannot disagree, and the variable-multiplicity exclusion (`Concept[]` never gates,
  because `[]` is its legitimate value) falls out of the descriptor's rule instead of being
  restated here.

Nested structures are judged **one level deep**: a required field that is itself an all-optional
object does not warn in this version (design §7 — the transitive notion's boundary is arguable, and
a lint whose boundary is arguable is a lint that gets ignored).
"""

from collections.abc import Iterable, Mapping

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipeline.input_form import InputFormField, PipeInputFormDescriptor
from pipelex.validation_error_types import PipeValidationErrorType


def build_vacuous_presence_warnings(
    *,
    input_form: Mapping[str, PipeInputFormDescriptor],
    entry_pipe_refs: Iterable[str],
) -> list[ValidationErrorItem]:
    """Project the entry pipes' input-form descriptors into advisory `warnings` items.

    Args:
        input_form: The batch's `input_form` descriptors, keyed by namespaced `pipe_ref`
            (the output of `build_input_form`).
        entry_pipe_refs: The domain-qualified refs of the batch's entry pipes. Refs with no
            descriptor are skipped, so a batch with no `main_pipe` is simply not linted.

    Returns:
        One `input_presence_vacuous` item per (entry pipe, gating slot whose concept demands
        nothing), ordered by entry pipe ref then by authored slot order.
    """
    warnings: list[ValidationErrorItem] = []
    for pipe_ref in sorted(set(entry_pipe_refs)):
        descriptor = input_form.get(pipe_ref)
        if descriptor is None:
            continue
        for slot in descriptor.fields:
            item = _warning_for_slot(pipe_ref=pipe_ref, slot=slot)
            if item is not None:
                warnings.append(item)
    return warnings


def _warning_for_slot(*, pipe_ref: str, slot: InputFormField) -> ValidationErrorItem | None:
    """The item a top-level slot earns, or `None` when the slot is silent."""
    if not slot.gating or not slot.kind.is_object:
        return None
    if any(field.required for field in slot.fields or []):
        return None
    concept_ref = slot.concept_ref
    if concept_ref is None:
        # No concept to name, hence no honest message to state: the lint's whole claim is about
        # what a named concept declares.
        return None
    # Split on the LAST dot: a domain is a dotted path ('legal.contracts'), so a leading-dot split
    # would hand the locator a truncated domain and a pipe code carrying the rest of it.
    locator = QualifiedRef.parse(pipe_ref)
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type=PipeValidationErrorType.INPUT_PRESENCE_VACUOUS,
        pipe_code=locator.local_code,
        domain_code=locator.domain_path,
        variable_names=[slot.name],
        message=_message(pipe_ref=pipe_ref, slot=slot, concept_ref=concept_ref),
    )


def _message(*, pipe_ref: str, slot: InputFormField, concept_ref: str) -> str:
    """The finding's prose: what was declared, why it enforces nothing, and the two remedies.

    Carries no authored free text (no descriptions), so it needs no eliding — unlike the hint lint,
    which interpolates authored content.
    """
    marker_desc = "declared with a force marker '!'" if slot.presence is not None and slot.presence.is_force else "declared without '?'"
    if slot.fields:
        defect = f"concept '{concept_ref}' declares no required field — an empty object satisfies it"
        second_remedy = f"make at least one field of '{concept_ref}' required"
    else:
        defect = f"concept '{concept_ref}' declares no field at all — an empty object satisfies it"
        second_remedy = f"give '{concept_ref}' a required field"
    return (
        f"Input '{slot.name}' of pipe '{pipe_ref}' must be supplied ({marker_desc}), but {defect}, "
        f"so a caller cannot tell what to fill in. "
        f'Mark the input optional (`{slot.name} = "{concept_ref}?"`) if the pipe can run without it, or {second_remedy}.'
    )
