"""What the value of a concept of a qualified crate is: text, a number, a date, a time, an image, a document, or none of them.

The one structural judgment the intent-hints lint and the contract-fact site checks share (spec: intent-hints.md,
"Applicability", and mthds-format.md, "Value Classes"): a description-only concept is text-valued, a native maps by its own
kind (`NativeConceptCode.site_value_kind`), a refinement chain classifies the refiner like the native it reaches, and a
class-backed concept like the native whose class it names. A structured concept holds no plain value.

A concept the crate cannot see, a cross-package reference or one an earlier load holds, is not classifiable here: `kind_of`
answers `None`, and each caller decides what an unknown site means for it (the lint stays quiet, the contract-fact checks
leave the site to the runtime's own validation).
"""

from collections.abc import Mapping

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.language.intent_hints import HintSiteValueKind


class ConceptJudgment:
    """A concept's value kind, and whether it holds a verdict (`YesNo`, `Choice`, `Rating`, or a refinement of one)."""

    def __init__(self, *, kind: HintSiteValueKind | None, is_verdict: bool) -> None:
        self.kind = kind
        self.is_verdict = is_verdict


class CrateConceptKinds:
    """Classifies the concepts of a qualified crate, caching each ref it judges once."""

    def __init__(self, *, concepts: Mapping[str, ConceptBlueprint | str]) -> None:
        self._concepts = concepts
        self._cache: dict[str, ConceptJudgment] = {}

    def kind_of(self, *, concept_ref: str) -> HintSiteValueKind | None:
        """The value kind of a concept, `None` when the crate cannot see it."""
        return self.judge(concept_ref=concept_ref).kind

    def kind_of_slot(self, *, concept_spec: str) -> HintSiteValueKind | None:
        """The value kind of an input slot's concept, judged per item: the multiplicity and presence markers strip away."""
        return self.kind_of(concept_ref=parse_concept_with_multiplicity(concept_spec).concept_ref_or_code)

    def is_verdict(self, *, concept_ref: str) -> bool:
        return self.judge(concept_ref=concept_ref).is_verdict

    def judge(self, *, concept_ref: str) -> ConceptJudgment:
        if concept_ref not in self._cache:
            self._cache[concept_ref] = self._resolve(concept_ref=concept_ref)
        return self._cache[concept_ref]

    def _resolve(self, *, concept_ref: str) -> ConceptJudgment:
        # Iterative on purpose, like every other chain walker: a legal, arbitrarily deep refinement chain must not be able
        # to raise a RecursionError out of a validation.
        seen: set[str] = set()
        current_ref = concept_ref
        while True:
            if current_ref in seen:
                # Defensive: a refinement cycle is refused upstream.
                return ConceptJudgment(kind=None, is_verdict=False)
            seen.add(current_ref)
            if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=current_ref):
                native_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=current_ref)
                native_code = NativeConceptCode(QualifiedRef.parse(native_ref).local_code)
                return ConceptJudgment(kind=native_code.site_value_kind, is_verdict=native_code.is_verdict_native)
            value = self._concepts.get(current_ref)
            if isinstance(value, str):
                # A string-described concept is description-only, hence text-valued.
                return ConceptJudgment(kind=HintSiteValueKind.TEXT_VALUED, is_verdict=False)
            if value is None:
                # A cross-package concept, or one an earlier load holds: not classifiable in this crate.
                return ConceptJudgment(kind=None, is_verdict=False)
            if value.refines:
                current_ref = value.refines
                continue
            if value.structure is None:
                return ConceptJudgment(kind=HintSiteValueKind.TEXT_VALUED, is_verdict=False)
            if isinstance(value.structure, str):
                # Class-backed: a native class name maps by identity to its native's kind; any other registered class
                # holds no plain value (L-260930-173b03 tracks a `RootModel` over a scalar, which the deriver reflects).
                class_native = next((code for code in NativeConceptCode if code.structure_class_name == value.structure), None)
                if class_native is None:
                    return ConceptJudgment(kind=HintSiteValueKind.OTHER, is_verdict=False)
                return ConceptJudgment(kind=class_native.site_value_kind, is_verdict=class_native.is_verdict_native)
            return ConceptJudgment(kind=HintSiteValueKind.OTHER, is_verdict=False)
