"""Neutral resolved-concept layer over a normalized library crate.

`resolve_concepts_from_crate` turns each concept in a normalized `LibraryCrate` into a
`ResolvedConcept` — the language-agnostic unit every types emitter (python-structures,
python-pydantic, ts-zod) consumes. Class naming (bare vs domain-qualified), the refinement base,
native flagging, structureless/imprecision detection, and field resolution (via the shared
`resolved_fields` layer) all live here, so no emitter re-derives them.

The crate is the single authority: this layer reads only the normalized crate — never the loader,
the class registry, or the raw bundles.
"""

from collections import Counter

from pydantic import BaseModel, ConfigDict

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.resolved_fields import ResolvedField, resolve_structure_fields
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.library_crate import LibraryCrate


class ResolvedConcept(BaseModel):
    """One crate concept resolved into the neutral shape a types emitter renders.

    Exactly one of these shapes holds: `fields` non-empty (a structured concept), `base_ref` set (a
    concept that still refines a structureless / cross-package base), or `structureless` (an opaque
    concept — string-described, Python-class-backed, or genuinely shape-less). `imprecision_reason`
    is set whenever the concept is opaque so the emitter surfaces a caveat instead of guessing a shape.
    """

    model_config = ConfigDict(frozen=True)

    concept_ref: str
    """Qualified ref: `domain.Code` or `native.Code`."""

    domain: str
    code: str
    """The local concept code (PascalCase), the seed of every target's type name."""

    description: str
    is_native: bool
    needs_qualification: bool
    """True when this code collides across domains, so every target must domain-qualify its type name."""

    base_ref: str | None
    """A refinement base still present in the normalized crate (qualified), else None."""

    fields: list[ResolvedField]
    structureless: bool
    imprecision_reason: str | None
    opaque_python_class: str | None
    """The Python class name for a `structure = "<ClassName>"` concept — opaque to a portable crate (B1-1 floor)."""


class ResolvedLibrary(BaseModel):
    """Every concept of one normalized crate, resolved and ordered by ref — the emitter input unit."""

    model_config = ConfigDict(frozen=True)

    mthds_version: str
    concepts: list[ResolvedConcept]

    def by_ref(self) -> dict[str, ResolvedConcept]:
        """Index the resolved concepts by their qualified ref (for base / field-reference lookups)."""
        return {concept.concept_ref: concept for concept in self.concepts}


def resolve_concepts_from_crate(crate: LibraryCrate) -> ResolvedLibrary:
    """Resolve every concept of a normalized crate into the neutral emitter input, sorted by ref.

    Collision detection is crate-wide: a bare code that appears in more than one domain forces
    domain-qualified naming for *every* concept carrying that code, in every target — so the
    definition and every reference agree on the spelling.
    """
    code_counts = Counter(QualifiedRef.parse(concept_ref).local_code for concept_ref in crate.concepts)
    available_refs = set(crate.concepts)
    concepts = [
        _resolve_concept(
            concept_ref,
            value=value,
            needs_qualification=code_counts[QualifiedRef.parse(concept_ref).local_code] > 1,
            available_refs=available_refs,
        )
        for concept_ref, value in sorted(crate.concepts.items())
    ]
    return ResolvedLibrary(mthds_version=crate.mthds_version, concepts=concepts)


def _resolve_concept(
    concept_ref: str,
    *,
    value: ConceptBlueprint | str,
    needs_qualification: bool,
    available_refs: set[str],
) -> ResolvedConcept:
    parsed = QualifiedRef.parse(concept_ref)
    domain = parsed.domain_path or ""
    code = parsed.local_code
    is_native = NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref)

    description: str
    base_ref: str | None = None
    fields: list[ResolvedField] = []
    structureless: bool
    imprecision_reason: str | None = None
    opaque_python_class: str | None = None

    if isinstance(value, str):
        # A normalized crate promotes string-described concepts to blueprints; handle the raw form
        # defensively so a hand-built crate still resolves.
        description = value
        structureless = True
        imprecision_reason = "concept is described by text only and declares no structure"
    elif isinstance(value.structure, str):
        # `structure = "<ClassName>"`: the shape lives only in hand-written Python, not in MTHDS, so it
        # is opaque to a portable crate. Surface it (never emit the bare class name silently) — B1-1 floor.
        description = value.description
        structureless = True
        opaque_python_class = value.structure
        imprecision_reason = f"concept is backed by the Python class '{value.structure}', which has no MTHDS structure to project"
    elif isinstance(value.structure, dict):
        description = value.description
        structureless = False
        fields = resolve_structure_fields(normalize_structure_blueprint(value.structure), local_domain=domain)
    elif value.refines:
        description = value.description
        base_ref = value.refines
        structureless = not (NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=value.refines) or value.refines in available_refs)
        if structureless:
            imprecision_reason = f"refinement base '{value.refines}' is not available in this crate"
    else:
        description = value.description
        structureless = True
        imprecision_reason = "concept declares no structure"

    return ResolvedConcept(
        concept_ref=concept_ref,
        domain=domain,
        code=code,
        description=description,
        is_native=is_native,
        needs_qualification=needs_qualification,
        base_ref=base_ref,
        fields=fields,
        structureless=structureless,
        imprecision_reason=imprecision_reason,
        opaque_python_class=opaque_python_class,
    )
