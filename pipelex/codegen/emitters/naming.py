"""Name-derivation rules shared by every types emitter (see `docs/specs/pipelex-codegen.md`).

A qualified concept `domain.Code` yields a type named from `Code` (already PascalCase) when that
code is unique across the crate; when the code collides across domains, the domain disambiguates.
The disambiguated spelling differs by target because identifier grammars differ:

- Python allows the interpunct `·` (U+00B7, an `Other_ID_Continue` code point), so it reuses the
  runtime seed `make_qualified_structure_class_name` (`legal.contracts` + `Result` -> `legal·contracts__Result`);
- TypeScript does not allow `·` in identifiers, so a colliding TS type PascalCases and joins the
  domain segments before the code (`legal.contracts` + `Result` -> `LegalContractsResult`).

Field names: the crate's snake_case is the wire contract. Python keeps it verbatim; TypeScript maps
it to camelCase and documents the wire name inline (a JSDoc `@wire` tag) so the round trip is exact.
"""

from pipelex.core.concepts.helpers import make_qualified_structure_class_name


def snake_to_pascal(name: str) -> str:
    """`snake_case` -> `PascalCase` (empty segments from stray underscores are dropped)."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def snake_to_camel(name: str) -> str:
    """`snake_case` -> `camelCase`, preserving the first segment's case."""
    parts = [part for part in name.split("_") if part]
    if not parts:
        return name
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


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
