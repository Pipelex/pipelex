"""Advisory intent-hints lints (`warnings`) for the validate surfaces (spec: intent-hints.md).

The spec's SHOULD-warn rules — an unknown hint key, an unknown `intent` word, a known word on a
site it does not apply to — cannot live in pydantic validators: a validator can only raise, and
these must never reject. Well-formed unknown content is preserved into the crate and the
descriptor untouched; the lint only names it. One advisory `ValidationErrorItem` per finding on
the report's `warnings` array, never flipping `is_valid` — composed with the other advisory
families in `advisory_warnings.py`, which is what every advisory-bearing validate channel calls.

Site applicability follows the spec's Applicability section: text-valued and number-valued sites
are judged structurally over the qualified crate (description-only concepts are text-valued;
refinement chains reaching `native.Text` / `native.Number` classify the refiner; plural sites are
judged per item). A site that is neither takes no word of this version.
"""

from enum import StrEnum

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.language.intent_hints import (
    INTENT_HINT_KEY,
    KNOWN_HINT_KEYS,
    PART_HINT_KEY,
    ROLE_HINT_KEY,
    FieldShape,
    HintSiteValueKind,
    IntentWord,
    PartWord,
    RoleWord,
    intent_applicable_kinds,
    intent_word_applies,
    is_intent_word_known,
    is_part_word_known,
    is_role_word_known,
    part_word_applies,
)
from pipelex.libraries.concept_value_kinds import CrateConceptKinds
from pipelex.libraries.crate_qualification import QualifiedCrateContent
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.validation_error_types import HintLintErrorType

MAX_HINT_FINDINGS_PER_SITE = 5
"""How many undefined hint keys one site reports individually before the rest collapse into a tail.

The unknown-key rule emits one finding per undefined key, so a site's finding count is bounded only
by how many keys the author wrote. That was tolerable while the lint reached the API path alone; it
now rides every advisory-bearing validate channel, including ones an author invokes casually, so a site that names fifty keys reports
the first few and then says how many more there were."""

MAX_AUTHORED_TOKEN_LENGTH = 60
"""How much of an authored hint key or value a message quotes before eliding the rest.

Hint keys and values are free strings, interpolated raw into the finding's `message`. Long enough to
identify the entry the author wrote, short enough that a whole document pasted into a hint value
cannot inflate the warning payload."""


def elide_authored_token(*, token: str) -> str:
    """An authored token, cut to a length a diagnostic can quote (an elided one ends in an ellipsis)."""
    if len(token) <= MAX_AUTHORED_TOKEN_LENGTH:
        return token
    return f"{token[:MAX_AUTHORED_TOKEN_LENGTH]}..."


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
        self._kinds = CrateConceptKinds(concepts=qualified.concepts)

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
                        site=_HintSite.CONCEPT,
                        site_desc=f"concept '{concept_ref}'",
                        domain_code=domain_code,
                        concept_code=concept_code,
                    )
                )
            if isinstance(value.structure, dict):
                part_holders: dict[PartWord, str] = {}
                for field_name, field in value.structure.items():
                    if isinstance(field, ConceptStructureBlueprint) and field.hints:
                        warnings.extend(
                            self._lint_hints(
                                hints=field.hints,
                                site_kind=self._field_site_kind(field),
                                site=_HintSite.FIELD,
                                field_shape=self._field_shape(field=field),
                                site_desc=f"field '{field_name}' of concept '{concept_ref}'",
                                domain_code=domain_code,
                                concept_code=concept_code,
                                field_name=field_name,
                                part_holders=part_holders,
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
                            site=_HintSite.SLOT,
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
        site: "_HintSite",
        site_desc: str,
        domain_code: str,
        field_shape: FieldShape = FieldShape.OTHER,
        concept_code: str | None = None,
        pipe_code: str | None = None,
        field_name: str | None = None,
        variable_names: list[str] | None = None,
        part_holders: dict[PartWord, str] | None = None,
    ) -> list[ValidationErrorItem]:
        # Each finding with the hint key it is about, elided as its message quotes it.
        findings: list[tuple[HintLintErrorType, str, str]] = []
        unknown_keys = [key for key in hints if key not in KNOWN_HINT_KEYS]
        for key in unknown_keys[:MAX_HINT_FINDINGS_PER_SITE]:
            unknown_key_message = (
                f"Hint key '{elide_authored_token(token=key)}' on {site_desc} is not defined by this version of the standard "
                f"(known keys: {', '.join(sorted(KNOWN_HINT_KEYS))}). The entry is preserved; consumers ignore it."
            )
            findings.append((HintLintErrorType.HINT_UNKNOWN_KEY, unknown_key_message, elide_authored_token(token=key)))
        overflow = len(unknown_keys) - MAX_HINT_FINDINGS_PER_SITE
        if overflow > 0:
            overflow_message = (
                f"...and {overflow} more hint key(s) on {site_desc} are not defined by this version of the standard. "
                f"The entries are preserved; consumers ignore them."
            )
            # The finding stands for every key past the cap, and names the first of them.
            first_overflow_key = elide_authored_token(token=unknown_keys[MAX_HINT_FINDINGS_PER_SITE])
            findings.append((HintLintErrorType.HINT_UNKNOWN_KEY, overflow_message, first_overflow_key))
        intent_word = hints.get(INTENT_HINT_KEY)
        if intent_word is not None:
            if not is_intent_word_known(intent_word):
                unknown_intent_message = (
                    f"Intent word '{elide_authored_token(token=intent_word)}' on {site_desc} is not in this version's vocabulary "
                    f"({', '.join(IntentWord)}). The entry is preserved; consumers ignore it."
                )
                findings.append((HintLintErrorType.HINT_UNKNOWN_INTENT, unknown_intent_message, INTENT_HINT_KEY))
            elif not intent_word_applies(known_word := IntentWord(intent_word), site_kind=site_kind):
                needed_kinds = " or ".join(sorted(kind.removesuffix("_valued") for kind in intent_applicable_kinds(word=known_word)))
                inapplicable_message = (
                    f"Intent word '{elide_authored_token(token=intent_word)}' does not apply to {site_desc} (the site is not "
                    f"{needed_kinds}-valued). The entry is preserved; consumers ignore it there."
                )
                findings.append((HintLintErrorType.HINT_INAPPLICABLE_INTENT, inapplicable_message, INTENT_HINT_KEY))
        role_word = hints.get(ROLE_HINT_KEY)
        if role_word is not None:
            if not is_role_word_known(word=role_word):
                unknown_role_message = (
                    f"Role word '{elide_authored_token(token=role_word)}' on {site_desc} is not in this version's vocabulary "
                    f"({', '.join(RoleWord)}). The entry is preserved; consumers ignore it."
                )
                findings.append((HintLintErrorType.HINT_UNKNOWN_ROLE, unknown_role_message, ROLE_HINT_KEY))
            elif not site.takes_role:
                inapplicable_role_message = (
                    f"Role word '{elide_authored_token(token=role_word)}' does not apply to {site_desc}: a role is said of an input slot only. "
                    "The entry is preserved; consumers ignore it there."
                )
                findings.append((HintLintErrorType.HINT_INAPPLICABLE_ROLE, inapplicable_role_message, ROLE_HINT_KEY))
        part_word = hints.get(PART_HINT_KEY)
        if part_word is not None:
            if not is_part_word_known(word=part_word):
                unknown_part_message = (
                    f"Part word '{elide_authored_token(token=part_word)}' on {site_desc} is not in this version's vocabulary "
                    f"({', '.join(PartWord)}). The entry is preserved; consumers ignore it."
                )
                findings.append((HintLintErrorType.HINT_UNKNOWN_PART, unknown_part_message, PART_HINT_KEY))
            elif not site.takes_part or not part_word_applies(word=(known_part := PartWord(part_word)), site_kind=site_kind, field_shape=field_shape):
                inapplicable_part_message = (
                    f"Part word '{elide_authored_token(token=part_word)}' does not apply to {site_desc}. "
                    "The entry is preserved; consumers ignore it there."
                )
                findings.append((HintLintErrorType.HINT_INAPPLICABLE_PART, inapplicable_part_message, PART_HINT_KEY))
            elif known_part.is_held_once and part_holders is not None and field_name is not None:
                first_holder = part_holders.setdefault(known_part, field_name)
                if first_holder != field_name:
                    duplicate_part_message = (
                        f"Part word '{known_part}' on {site_desc} is already held by field '{first_holder}': one field of a structure "
                        f"at most is its {known_part}. The entry is preserved."
                    )
                    findings.append((HintLintErrorType.HINT_DUPLICATE_PART, duplicate_part_message, PART_HINT_KEY))
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
                hint_key=hint_key,
            )
            for error_type, message, hint_key in findings
        ]

    # ---- Site classification (spec: Applicability) ------------------------------------------------

    def _concept_site_kind(self, concept_ref: str) -> HintSiteValueKind:
        # A concept the crate cannot see takes no word of this version, as before.
        return self._kinds.kind_of(concept_ref=concept_ref) or HintSiteValueKind.OTHER

    def _field_shape(self, *, field: ConceptStructureBlueprint) -> FieldShape:
        """The shape of a field that decides where a `part` word applies, judged against the field, never a list's item."""
        if field.choices:
            return FieldShape.ENUMERATION
        match field.type:
            case ConceptStructureBlueprintFieldType.BOOLEAN:
                return FieldShape.BOOLEAN
            case ConceptStructureBlueprintFieldType.LIST:
                return FieldShape.LIST
            case ConceptStructureBlueprintFieldType.DICT:
                return FieldShape.OTHER
            case ConceptStructureBlueprintFieldType.CONCEPT:
                if field.concept_ref and self._kinds.is_verdict(concept_ref=field.concept_ref):
                    return FieldShape.VERDICT_NATIVE
                return FieldShape.SCALAR
            case (
                ConceptStructureBlueprintFieldType.TEXT
                | ConceptStructureBlueprintFieldType.INTEGER
                | ConceptStructureBlueprintFieldType.NUMBER
                | ConceptStructureBlueprintFieldType.DATE
                | ConceptStructureBlueprintFieldType.DATETIME
                | ConceptStructureBlueprintFieldType.TIME
                | None
            ):
                return FieldShape.SCALAR

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
                    case ConceptStructureBlueprintFieldType.TEXT:
                        return HintSiteValueKind.TEXT_VALUED
                    case ConceptStructureBlueprintFieldType.INTEGER | ConceptStructureBlueprintFieldType.NUMBER:
                        return HintSiteValueKind.NUMBER_VALUED
                    case ConceptStructureBlueprintFieldType.CONCEPT:
                        return self._concept_site_kind(field.item_concept_ref) if field.item_concept_ref else HintSiteValueKind.OTHER
                    case _:
                        # Any other item type (a nested list or dict, a scalar of another kind, the `Any` sentinel, none) is OTHER.
                        return HintSiteValueKind.OTHER
            case (
                ConceptStructureBlueprintFieldType.DICT
                | ConceptStructureBlueprintFieldType.BOOLEAN
                | ConceptStructureBlueprintFieldType.DATE
                | ConceptStructureBlueprintFieldType.DATETIME
                | ConceptStructureBlueprintFieldType.TIME
                | None
            ):
                # No type (choices-only), dict, boolean, date/datetime/time: neither text- nor number-valued.
                return HintSiteValueKind.OTHER

    def _slot_site_kind(self, concept_spec: str) -> HintSiteValueKind:
        # Multiplicity is a plural site judged per item, and the item is the slot's concept —
        # so the markers simply strip away.
        return self._kinds.kind_of_slot(concept_spec=concept_spec) or HintSiteValueKind.OTHER

    @staticmethod
    def _split_ref(qualified_ref: str) -> tuple[str, str]:
        parsed = QualifiedRef.parse(qualified_ref)
        return parsed.domain_path or "", parsed.local_code


class _HintSite(StrEnum):
    """The three sites a hint attaches to, which decide where `role` and `part` apply."""

    CONCEPT = "concept"
    FIELD = "field"
    SLOT = "slot"

    @property
    def takes_role(self) -> bool:
        match self:
            case _HintSite.SLOT:
                return True
            case _HintSite.CONCEPT | _HintSite.FIELD:
                return False

    @property
    def takes_part(self) -> bool:
        match self:
            case _HintSite.FIELD:
                return True
            case _HintSite.CONCEPT | _HintSite.SLOT:
                return False
