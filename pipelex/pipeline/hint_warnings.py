"""Advisory intent-hints lints (`warnings`) for the validate surfaces (spec: intent-hints.md).

The spec's SHOULD-warn rules — an unknown hint key, an unknown `intent` word, a known word on a
site it does not apply to — cannot live in pydantic validators: a validator can only raise, and
these must never reject. Well-formed unknown content is preserved into the crate and the
descriptor untouched; the lint only names it. Same channel as `build_optionality_warnings`: one
advisory `ValidationErrorItem` per finding on the report's `warnings` array, never flipping
`is_valid`.

Site applicability follows the spec's Applicability section: text-valued and number-valued sites
are judged structurally over the qualified crate (description-only concepts are text-valued;
refinement chains reaching `native.Text` / `native.Number` classify the refiner; plural sites are
judged per item). A site that is neither takes no word of this version.
"""

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.interpreter_hub import get_current_library_id_or_none, get_library_manager
from pipelex.language.intent_hints import (
    INTENT_HINT_KEY,
    KNOWN_HINT_KEYS,
    HintSiteValueKind,
    IntentWord,
    intent_word_applies,
    is_intent_word_known,
)
from pipelex.libraries.crate_qualification import QualifiedCrateContent, qualify_crate
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.validation_error_types import HintLintErrorType

_NATIVE_TEXT_REF = "native.Text"
_NATIVE_NUMBER_REF = "native.Number"


def _native_class_value_kind(*, class_name: str) -> HintSiteValueKind:
    """The value kind of a class-backed structure, by native-class identity.

    Mirrors the deriver's `_class_backed_node` lookup: `TextContent` is the native Text payload
    (text-valued), `NumberContent` the native Number payload (number-valued). Every other class —
    the remaining natives and registered project classes alike — is not a hint-applicable site.
    """
    native_code = next((code for code in NativeConceptCode if code.structure_class_name == class_name), None)
    match native_code:
        case NativeConceptCode.TEXT:
            return HintSiteValueKind.TEXT_VALUED
        case NativeConceptCode.NUMBER:
            return HintSiteValueKind.NUMBER_VALUED
        case (
            NativeConceptCode.DYNAMIC
            | NativeConceptCode.IMAGE
            | NativeConceptCode.DOCUMENT
            | NativeConceptCode.HTML
            | NativeConceptCode.TEXT_AND_IMAGES
            | NativeConceptCode.YES_NO
            | NativeConceptCode.DATE
            | NativeConceptCode.TIME
            | NativeConceptCode.PAGE
            | NativeConceptCode.JSON
            | NativeConceptCode.SEARCH_RESULT
            | NativeConceptCode.ANYTHING
            | NativeConceptCode.COMPOSITE
            | None
        ):
            return HintSiteValueKind.OTHER


def build_current_library_hint_warnings() -> list[ValidationErrorItem]:
    """Hint lint over the current library's accumulated crate.

    Same window contract as `build_input_form`; with no current library or no crate the sweep
    is empty (the fallback path derives nothing to lint).
    """
    library_id = get_current_library_id_or_none()
    crate = get_library_manager().get_crate(library_id=library_id) if library_id else None
    if crate is None:
        return []
    return build_hint_warnings(qualify_crate(crate))


def build_hint_warnings(qualified: QualifiedCrateContent) -> list[ValidationErrorItem]:
    """Sweep the qualified crate's three hint sites and emit one advisory item per finding.

    Args:
        qualified: The qualified crate content (in-body refs resolved, so concept classification
            can follow refinement chains by qualified key).

    Returns:
        Advisory items in deterministic order: concepts (by qualified ref, fields in authored
        order), then pipes (by qualified ref, slots in authored order).
    """
    linter = _HintLinter(qualified=qualified)
    return linter.lint()


class _HintLinter:
    def __init__(self, *, qualified: QualifiedCrateContent) -> None:
        self._concepts = qualified.concepts
        self._pipes = qualified.pipes
        self._concept_kind_cache: dict[str, HintSiteValueKind] = {}

    def lint(self) -> list[ValidationErrorItem]:
        warnings: list[ValidationErrorItem] = []
        for concept_ref in sorted(self._concepts):
            value = self._concepts[concept_ref]
            if not isinstance(value, ConceptBlueprint):
                continue
            domain_code, concept_code = self._split_ref(concept_ref)
            if value.hints:
                warnings.extend(
                    self._lint_hints(
                        hints=value.hints,
                        site_kind=self._concept_site_kind(concept_ref),
                        site_desc=f"concept '{concept_ref}'",
                        domain_code=domain_code,
                        concept_code=concept_code,
                    )
                )
            if isinstance(value.structure, dict):
                for field_name, field in value.structure.items():
                    if isinstance(field, ConceptStructureBlueprint) and field.hints:
                        warnings.extend(
                            self._lint_hints(
                                hints=field.hints,
                                site_kind=self._field_site_kind(field),
                                site_desc=f"field '{field_name}' of concept '{concept_ref}'",
                                domain_code=domain_code,
                                concept_code=concept_code,
                                field_name=field_name,
                            )
                        )
        for pipe_ref in sorted(self._pipes):
            blueprint = self._pipes[pipe_ref]
            if not blueprint.inputs:
                continue
            domain_code, pipe_code = self._split_ref(pipe_ref)
            for slot_name, slot_value in blueprint.inputs.items():
                if isinstance(slot_value, InputSlotBlueprint) and slot_value.hints:
                    warnings.extend(
                        self._lint_hints(
                            hints=slot_value.hints,
                            site_kind=self._slot_site_kind(slot_value.concept),
                            site_desc=f"input '{slot_name}' of pipe '{pipe_ref}'",
                            domain_code=domain_code,
                            pipe_code=pipe_code,
                            variable_names=[slot_name],
                        )
                    )
        return warnings

    # ---- Per-site linting -------------------------------------------------------------------------

    def _lint_hints(
        self,
        *,
        hints: dict[str, str],
        site_kind: HintSiteValueKind,
        site_desc: str,
        domain_code: str,
        concept_code: str | None = None,
        pipe_code: str | None = None,
        field_name: str | None = None,
        variable_names: list[str] | None = None,
    ) -> list[ValidationErrorItem]:
        findings: list[tuple[HintLintErrorType, str]] = []
        for key in hints:
            if key not in KNOWN_HINT_KEYS:
                unknown_key_message = (
                    f"Hint key '{key}' on {site_desc} is not defined by this version of the standard "
                    f"(known keys: {', '.join(sorted(KNOWN_HINT_KEYS))}). The entry is preserved; consumers ignore it."
                )
                findings.append((HintLintErrorType.HINT_UNKNOWN_KEY, unknown_key_message))
        intent_word = hints.get(INTENT_HINT_KEY)
        if intent_word is not None:
            if not is_intent_word_known(intent_word):
                unknown_intent_message = (
                    f"Intent word '{intent_word}' on {site_desc} is not in this version's vocabulary "
                    f"(prose, label, rating, quantity). The entry is preserved; consumers ignore it."
                )
                findings.append((HintLintErrorType.HINT_UNKNOWN_INTENT, unknown_intent_message))
            elif not intent_word_applies(known_word := IntentWord(intent_word), site_kind=site_kind):
                match known_word:
                    case IntentWord.PROSE | IntentWord.LABEL:
                        needed_kind = "text"
                    case IntentWord.RATING | IntentWord.QUANTITY:
                        needed_kind = "number"
                inapplicable_message = (
                    f"Intent word '{intent_word}' does not apply to {site_desc} (the site is not "
                    f"{needed_kind}-valued). The entry is preserved; consumers ignore it there."
                )
                findings.append((HintLintErrorType.HINT_INAPPLICABLE_INTENT, inapplicable_message))
        return [
            ValidationErrorItem(
                category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
                error_type=error_type,
                message=message,
                domain_code=domain_code,
                concept_code=concept_code,
                pipe_code=pipe_code,
                field_name=field_name,
                variable_names=variable_names,
            )
            for error_type, message in findings
        ]

    # ---- Site classification (spec: Applicability) ------------------------------------------------

    def _concept_site_kind(self, concept_ref: str) -> HintSiteValueKind:
        if concept_ref in self._concept_kind_cache:
            return self._concept_kind_cache[concept_ref]
        kind = self._resolve_concept_kind(concept_ref, seen=set())
        self._concept_kind_cache[concept_ref] = kind
        return kind

    def _resolve_concept_kind(self, concept_ref: str, *, seen: set[str]) -> HintSiteValueKind:
        if concept_ref in seen:
            return HintSiteValueKind.OTHER  # defensive: cycles are rejected upstream
        seen.add(concept_ref)
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
            native_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref)
            if native_ref == _NATIVE_TEXT_REF:
                return HintSiteValueKind.TEXT_VALUED
            if native_ref == _NATIVE_NUMBER_REF:
                return HintSiteValueKind.NUMBER_VALUED
            return HintSiteValueKind.OTHER
        value = self._concepts.get(concept_ref)
        if isinstance(value, str):
            # String-described concept: description-only, hence text-valued.
            return HintSiteValueKind.TEXT_VALUED
        if not isinstance(value, ConceptBlueprint):
            # Cross-package or unknown: not classifiable in-crate.
            return HintSiteValueKind.OTHER
        if value.refines:
            return self._resolve_concept_kind(value.refines, seen=seen)
        if value.structure is None:
            # Description-only concepts are text-valued per the spec.
            return HintSiteValueKind.TEXT_VALUED
        if isinstance(value.structure, str):
            # Class-backed: a native class name maps by identity to its native's value kind, the
            # same judgment the input-form deriver makes — so the lint never calls a hint
            # inapplicable that the descriptor then honors. Any other registered class is an
            # object payload, hence OTHER.
            return _native_class_value_kind(class_name=value.structure)
        return HintSiteValueKind.OTHER

    def _field_site_kind(self, field: ConceptStructureBlueprint) -> HintSiteValueKind:
        if field.choices:
            # Choices dominate the declared type (the deriver and the structure generator agree):
            # the payload is an enum, which no intent word applies to.
            return HintSiteValueKind.OTHER
        match field.type:
            case ConceptStructureBlueprintFieldType.TEXT:
                return HintSiteValueKind.TEXT_VALUED
            case ConceptStructureBlueprintFieldType.INTEGER | ConceptStructureBlueprintFieldType.NUMBER:
                return HintSiteValueKind.NUMBER_VALUED
            case ConceptStructureBlueprintFieldType.CONCEPT:
                return self._concept_site_kind(field.concept_ref) if field.concept_ref else HintSiteValueKind.OTHER
            case ConceptStructureBlueprintFieldType.LIST:
                # Plural site: judged against the item as if it stood alone.
                match field.item_type:
                    case "text":
                        return HintSiteValueKind.TEXT_VALUED
                    case "integer" | "number":
                        return HintSiteValueKind.NUMBER_VALUED
                    case "concept":
                        return self._concept_site_kind(field.item_concept_ref) if field.item_concept_ref else HintSiteValueKind.OTHER
                    case _:
                        return HintSiteValueKind.OTHER
            case _:
                # No type (choices), dict, boolean, date/datetime/time: neither text- nor number-valued.
                return HintSiteValueKind.OTHER

    def _slot_site_kind(self, concept_spec: str) -> HintSiteValueKind:
        # Multiplicity is a plural site judged per item, and the item is the slot's concept —
        # so the markers simply strip away.
        parsed = parse_concept_with_multiplicity(concept_spec)
        return self._concept_site_kind(parsed.concept_ref_or_code)

    @staticmethod
    def _split_ref(qualified_ref: str) -> tuple[str, str]:
        parsed = QualifiedRef.parse(qualified_ref)
        return parsed.domain_path or "", parsed.local_code
