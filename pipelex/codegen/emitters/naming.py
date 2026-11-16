"""Name-derivation rules shared by every types emitter (see the codegen spec).

A qualified concept `domain.Code` yields a type named from `Code` (already PascalCase) when that
code is unique across the crate; when the code collides across domains, the domain disambiguates.
The disambiguated spelling differs by target because identifier grammars differ:

- Python allows the interpunct `·` (U+00B7, an `Other_ID_Continue` code point), so it reuses the
  runtime seed `make_qualified_structure_class_name` (`legal.contracts` + `Result` -> `legal·contracts__Result`);
- TypeScript does not allow `·` in identifiers, so a colliding TS type PascalCases and joins the
  domain segments before the code (`legal.contracts` + `Result` -> `LegalContractsResult`). Because
  that spelling is not injective, the TypeScript emitter allocates the final names crate-wide and
  adds deterministic numeric suffixes when distinct concepts still produce the same candidate.

A concept whose wire shape differs from its loaded shape (see `pipelex.codegen.resolved_concepts`) gets a second
type for its wire shape, named after the loaded type with `Wire` appended (`Text` -> `TextWire`). When that name is
already an emitted type's, a numeric suffix follows it (`ReportWire2`), so the authored concept keeps its name.

Field names: the crate's snake_case is the wire contract, and every target keeps it verbatim (D10:
wire-native keys — a TS schema validates the wire payload directly, no key remapping layer).
"""

from collections.abc import Callable

from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary
from pipelex.core.concepts.helpers import make_qualified_structure_class_name


def snake_to_pascal(name: str) -> str:
    """`snake_case` -> `PascalCase` (empty segments from stray underscores are dropped)."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def python_class_name(*, domain: str, code: str, needs_qualification: bool) -> str:
    """The Python class name for a concept: bare `Code`, or the runtime domain-qualified spelling."""
    if not needs_qualification:
        return code
    return make_qualified_structure_class_name(domain_code=domain, concept_code=code)


def allocate_python_class_names(*, library: ResolvedLibrary) -> dict[str, str]:
    """The Python class name of every concept and every wire shape of the library, by ref."""
    names_by_ref = {
        concept.concept_ref: python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
        for concept in library.concepts
    }
    used_names = set(names_by_ref.values())
    for wire_shape in library.wire_shapes:
        wire_name = _free_wire_name(loaded_name=names_by_ref[_loaded_ref(wire_shape=wire_shape)], is_free=lambda name: name not in used_names)
        names_by_ref[wire_shape.concept_ref] = wire_name
        used_names.add(wire_name)
    return names_by_ref


def _loaded_ref(*, wire_shape: ResolvedConcept) -> str:
    """The ref of the concept a wire shape is the wire shape of."""
    if wire_shape.wire_shape_of is None:
        msg = f"'{wire_shape.concept_ref}' is a concept's loaded shape, not a wire shape"
        raise ValueError(msg)
    return wire_shape.wire_shape_of


def _free_wire_name(*, loaded_name: str, is_free: Callable[[str], bool]) -> str:
    """`<loaded>Wire`, or `<loaded>Wire<N>` with the smallest N from 2 that makes it free."""
    candidate = f"{loaded_name}Wire"
    wire_name = candidate
    suffix = 2
    while not is_free(wire_name):
        wire_name = f"{candidate}{suffix}"
        suffix += 1
    return wire_name


def ts_type_name(*, domain: str, code: str, needs_qualification: bool) -> str:
    """Derive a TypeScript name candidate; use `allocate_ts_type_names` for final emitted names."""
    if not needs_qualification:
        return code
    domain_pascal = "".join(snake_to_pascal(segment) for segment in domain.split("."))
    return f"{domain_pascal}{code}"


def allocate_ts_type_names(library: ResolvedLibrary) -> dict[str, str]:
    """Allocate one unique, deterministic TypeScript type name per concept reference.

    A bare concept keeps its authored code when it collides with a generated qualified candidate.
    Other ties are settled by qualified ref, independent of input order. Numeric suffix allocation
    reserves every unsuffixed candidate first, so a disambiguated name cannot steal another
    concept's natural candidate. Each allocated type also reserves its derived `<Type>Schema`
    identifier because both names are imported together by the binder. Wire shapes are allocated after every
    concept, each from its loaded type's final name.
    """
    concepts_by_candidate: dict[str, list[ResolvedConcept]] = {}
    for concept in library.concepts:
        candidate = ts_type_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
        concepts_by_candidate.setdefault(candidate, []).append(concept)

    reserved_names = set(concepts_by_candidate)
    used_symbols: set[str] = set()
    allocated_by_ref: dict[str, str] = {}
    for candidate, concepts in sorted(concepts_by_candidate.items()):
        ordered_concepts = sorted(concepts, key=lambda concept: (concept.needs_qualification, concept.concept_ref))
        suffix = 2
        for concept_index, concept in enumerate(ordered_concepts):
            if concept_index == 0 and _ts_symbols_are_free(candidate, used_symbols=used_symbols):
                allocated_name = candidate
            else:
                allocated_name = f"{candidate}{suffix}"
                while (
                    not _ts_symbols_are_free(allocated_name, used_symbols=used_symbols)
                    or allocated_name in reserved_names
                    or f"{allocated_name}Schema" in reserved_names
                ):
                    suffix += 1
                    allocated_name = f"{candidate}{suffix}"
                suffix += 1
            allocated_by_ref[concept.concept_ref] = allocated_name
            used_symbols.add(allocated_name)
            used_symbols.add(f"{allocated_name}Schema")

    # The wire shapes come after every concept, so a concept's name never depends on whether a wire shape exists.
    for wire_shape in library.wire_shapes:
        wire_name = _free_wire_name(
            loaded_name=allocated_by_ref[_loaded_ref(wire_shape=wire_shape)],
            is_free=lambda name: _ts_symbols_are_free(name, used_symbols=used_symbols) and name not in reserved_names,
        )
        allocated_by_ref[wire_shape.concept_ref] = wire_name
        used_symbols.add(wire_name)
        used_symbols.add(f"{wire_name}Schema")

    return allocated_by_ref


def _ts_symbols_are_free(type_name: str, *, used_symbols: set[str]) -> bool:
    """Whether a type and its derived schema identifier are both unclaimed."""
    return type_name not in used_symbols and f"{type_name}Schema" not in used_symbols
