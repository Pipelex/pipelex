"""Neutral resolved-concept layer over a normalized library crate.

`resolve_concepts_from_crate` turns each concept in a normalized `LibraryCrate` into a
`ResolvedConcept` — the language-agnostic unit every types emitter (python-structures,
python-pydantic, ts-zod) consumes. Class naming (bare vs domain-qualified), the refinement base,
native flagging, structureless/imprecision detection, and field resolution (via the shared
`resolved_fields` layer) all live here, so no emitter re-derives them.

The crate is the single authority: this layer reads only the normalized crate — never the loader,
the class registry, or the raw bundles.

**Two shapes of a stored value.** `Text` (with `Markdown`), `Html` and `JSON` may hold their value in the run's
storage, in which case the wire carries a reference (`url`, `size`, `mime_type`, `preview`) in place of the value.
Our clients load every stored value before they hand a result back, so the shape a caller usually parses is the
**loaded** one: a concept's own fields, with a storable native reduced to its value, required (`text: str`). That is
what `ResolvedLibrary.concepts` holds. The **wire** shape, either form of the value as the crate's native states it,
is what a caller who keeps the references parses: `ResolvedLibrary.wire_shapes` holds one for every concept whose
wire shape differs from its loaded one, which is a storable native and every concept reaching one through a field,
a list or dict item, or a refinement. A wire shape's references to such concepts point at their wire shapes, and its
`concept_ref` is its loaded concept's ref with `WIRE_SHAPE_REF_SUFFIX`, which no authored concept can carry.
"""

from collections import Counter

from pydantic import BaseModel, ConfigDict

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_native_value_structure
from pipelex.core.concepts.resolved_fields import ResolvedField, ResolvedType, resolve_structure_fields
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

    wire_shape_of: str | None = None
    """Set on a wire shape only: the qualified ref of the concept whose wire shape this is."""

    stored_value_wire_fields: list[ResolvedField] | None = None
    """On a native that may hold its value in storage: every field the crate states, the reference's included.

    Its `fields` are then the value alone, the loaded shape, and these are what its wire shape is built from.
    """


class ResolvedLibrary(BaseModel):
    """Every concept of one normalized crate, resolved and ordered by ref — the emitter input unit."""

    model_config = ConfigDict(frozen=True)

    mthds_version: str
    concepts: list[ResolvedConcept]
    """Every concept of the crate in its loaded shape, sorted by ref."""

    wire_shapes: list[ResolvedConcept] = []
    """The wire shape of every concept whose wire shape differs from its loaded one, sorted by the loaded concept's ref."""

    def by_ref(self) -> dict[str, ResolvedConcept]:
        """Index the resolved concepts and wire shapes by their ref (for base / field-reference lookups)."""
        return {concept.concept_ref: concept for concept in [*self.concepts, *self.wire_shapes]}


# Appended to a concept's ref to make its wire shape's: `#` never appears in a concept ref, so no authored concept collides.
WIRE_SHAPE_REF_SUFFIX = "#wire"


def wire_shape_ref(*, concept_ref: str) -> str:
    """The ref of a concept's wire shape."""
    return f"{concept_ref}{WIRE_SHAPE_REF_SUFFIX}"


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
    return ResolvedLibrary(mthds_version=crate.mthds_version, concepts=concepts, wire_shapes=_make_wire_shapes(concepts=concepts))


def _make_wire_shapes(*, concepts: list[ResolvedConcept]) -> list[ResolvedConcept]:
    """The wire shape of every concept whose wire shape differs from its loaded one, in the order of `concepts`.

    The set starts at the storable natives and grows to a fixed point over every concept reaching one of its members
    through its refinement base or a field type.
    """
    wire_shaped_refs = {concept.concept_ref for concept in concepts if concept.stored_value_wire_fields is not None}
    is_growing = True
    while is_growing:
        is_growing = False
        for concept in concepts:
            if concept.concept_ref in wire_shaped_refs:
                continue
            reached_refs: set[str] = {concept.base_ref} if concept.base_ref is not None else set()
            for concept_field in concept.fields:
                reached_refs.update(_type_concept_refs(resolved_type=concept_field.resolved_type))
            if reached_refs & wire_shaped_refs:
                wire_shaped_refs.add(concept.concept_ref)
                is_growing = True

    wire_shapes: list[ResolvedConcept] = []
    for concept in concepts:
        if concept.concept_ref not in wire_shaped_refs:
            continue
        source_fields = concept.stored_value_wire_fields if concept.stored_value_wire_fields is not None else concept.fields
        wire_fields = [
            concept_field.model_copy(
                update={"resolved_type": _to_wire_type(resolved_type=concept_field.resolved_type, wire_shaped_refs=wire_shaped_refs)}
            )
            for concept_field in source_fields
        ]
        base_ref = concept.base_ref
        if base_ref is not None and base_ref in wire_shaped_refs:
            base_ref = wire_shape_ref(concept_ref=base_ref)
        wire_shapes.append(
            concept.model_copy(
                update={
                    "concept_ref": wire_shape_ref(concept_ref=concept.concept_ref),
                    "wire_shape_of": concept.concept_ref,
                    "base_ref": base_ref,
                    "fields": wire_fields,
                    "stored_value_wire_fields": None,
                }
            )
        )
    return wire_shapes


def _type_concept_refs(*, resolved_type: ResolvedType) -> set[str]:
    """Every concept a resolved type names, at any depth."""
    concept_refs: set[str] = {resolved_type.concept_ref} if resolved_type.concept_ref is not None else set()
    for child_type in (resolved_type.item, resolved_type.key, resolved_type.value):
        if child_type is not None:
            concept_refs.update(_type_concept_refs(resolved_type=child_type))
    return concept_refs


def _to_wire_type(*, resolved_type: ResolvedType, wire_shaped_refs: set[str]) -> ResolvedType:
    """The resolved type with every reference to a wire-shaped concept pointing at its wire shape."""
    update: dict[str, ResolvedType | str] = {}
    if resolved_type.concept_ref is not None and resolved_type.concept_ref in wire_shaped_refs:
        update["concept_ref"] = wire_shape_ref(concept_ref=resolved_type.concept_ref)
    for attribute_name in ("item", "key", "value"):
        child_type: ResolvedType | None = getattr(resolved_type, attribute_name)
        if child_type is not None:
            update[attribute_name] = _to_wire_type(resolved_type=child_type, wire_shaped_refs=wire_shaped_refs)
    return resolved_type.model_copy(update=update)


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
    stored_value_wire_fields: list[ResolvedField] | None = None

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
        value_structure: dict[str, ConceptStructureBlueprintType] | None = None
        if is_native:
            native_code = NativeConceptCode(code)
            value_structure = make_native_value_structure(native_code, structure=value.structure)
        if value_structure is not None:
            # A storable native: its loaded shape is its value alone, its wire shape every field the crate states.
            stored_value_wire_fields = fields
            fields = resolve_structure_fields(normalize_structure_blueprint(value_structure), local_domain=domain)
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
        stored_value_wire_fields=stored_value_wire_fields,
    )
