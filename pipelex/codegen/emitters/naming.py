"""Name-derivation rules shared by every types emitter (see `docs/specs/pipelex-codegen.md`).

A qualified concept `domain.Code` yields a type named from `Code` (already PascalCase) when that
code is unique across the crate; when the code collides across domains, the domain disambiguates.
The disambiguated spelling differs by target because identifier grammars differ:

- Python allows the interpunct `·` (U+00B7, an `Other_ID_Continue` code point), so it reuses the
  runtime seed `make_qualified_structure_class_name` (`legal.contracts` + `Result` -> `legal·contracts__Result`);
- TypeScript does not allow `·` in identifiers, so a colliding TS type PascalCases and joins the
  domain segments before the code (`legal.contracts` + `Result` -> `LegalContractsResult`).

Field names: the crate's snake_case is the wire contract, and every target keeps it verbatim (D10:
wire-native keys — a TS schema validates the wire payload directly, no key remapping layer).
"""

from pipelex.codegen.resolved_concepts import ResolvedLibrary
from pipelex.core.concepts.helpers import make_qualified_structure_class_name


def snake_to_pascal(name: str) -> str:
    """`snake_case` -> `PascalCase` (empty segments from stray underscores are dropped)."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def python_class_name(*, domain: str, code: str, needs_qualification: bool) -> str:
    """The Python class name for a concept: bare `Code`, or the runtime domain-qualified spelling."""
    if not needs_qualification:
        return code
    return make_qualified_structure_class_name(domain_code=domain, concept_code=code)


def ts_type_name(*, domain: str, code: str, needs_qualification: bool) -> str:
    """The TypeScript type name for a concept: bare `Code`, or PascalCased domain segments + `Code`."""
    if not needs_qualification:
        return code
    domain_pascal = "".join(snake_to_pascal(segment) for segment in domain.split("."))
    return f"{domain_pascal}{code}"


def runtime_to_emitted_class_names(library: ResolvedLibrary) -> dict[str, str]:
    """Map each concept's runtime structure-class name to its emitted Python class name.

    The runtime materializes every non-native concept under the domain-qualified spelling
    (`make_qualified_structure_class_name`), while the Python emitters name bare-when-unique — this
    mapping lets a consumer (the runner-script generator) spell classes the way the emitted
    projection defines them. Opaque Python-backed concepts (`structure = "<ClassName>"`) keep the
    user's real class at runtime, so they are deliberately not remapped.
    """
    mapping: dict[str, str] = {}
    for concept in library.concepts:
        if concept.is_native or concept.opaque_python_class:
            continue
        runtime_name = make_qualified_structure_class_name(domain_code=concept.domain, concept_code=concept.code)
        mapping[runtime_name] = python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
    return mapping
