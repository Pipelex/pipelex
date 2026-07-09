"""python-pydantic emitter: project a crate's concept set as plain `pydantic.BaseModel` types.

The neutral type projection — the same shapes as python-structures but with no Pipelex imports and
no `StructuredContent` base, so the generated module depends only on `pydantic` (and stdlib). Every
concept in the crate is emitted uniformly, including the materialized natives (`native.Text` becomes
a `Text` model), so the file is self-contained: a consumer needs the crate and pydantic, nothing else.

Modern typing throughout: builtin generics (`list` / `dict`), `X | None` for optionals, and
`from __future__ import annotations` so concept references resolve as forward names from the module.
"""

from pipelex.codegen.emitters.naming import python_class_name
from pipelex.codegen.emitters.python_common import any_annotation, class_docstring, field_line, order_by_base, python_header
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary
from pipelex.codegen.resolved_fields import ResolvedField, ResolvedType, ResolvedTypeKind

_FILENAME = "models.py"


def emit_python_pydantic(library: ResolvedLibrary) -> list[EmittedFile]:
    """Emit the `models.py` module: one plain `BaseModel` per concept (natives included)."""
    by_ref = library.by_ref()
    in_module = {concept.concept_ref for concept in library.concepts}
    ordered = order_by_base(library.concepts, in_module=in_module)

    imports: set[str] = {"from pydantic import BaseModel, Field"}
    blocks = [_render_class(concept, by_ref=by_ref, imports=imports) for concept in ordered]

    header = python_header(target="python-pydantic")
    import_block = "\n".join(sorted(imports))
    body = f"{header}from __future__ import annotations\n\n{import_block}\n\n\n" + "\n\n\n".join(blocks) + "\n"
    return [EmittedFile(filename=_FILENAME, content=body)]


def _render_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    class_name = python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
    base = _base_class(concept, by_ref=by_ref)
    caveat = f"Imprecise: {concept.imprecision_reason}." if concept.structureless and concept.imprecision_reason else None
    docstring = class_docstring(concept.description, extra_line=caveat)
    header = f"class {class_name}({base}):"
    if not concept.fields:
        return f"{header}\n{docstring}"
    lines = [_render_field(concept_field, by_ref=by_ref, imports=imports) for concept_field in concept.fields]
    return f"{header}\n{docstring}\n\n" + "\n".join(lines)


def _base_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept]) -> str:
    if concept.base_ref is None:
        return "BaseModel"
    base = by_ref.get(concept.base_ref)
    if base is not None:
        return python_class_name(domain=base.domain, code=base.code, needs_qualification=base.needs_qualification)
    # Cross-package / unknown base is not resolvable in-crate: fall back to a structurally valid root.
    return "BaseModel"


def _render_field(concept_field: ResolvedField, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    annotation = _annotation(concept_field.resolved_type, by_ref=by_ref, imports=imports)
    if not concept_field.required:
        annotation = f"{annotation} | None"
    return field_line(concept_field, annotation=annotation)


def _annotation(resolved_type: ResolvedType, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    match resolved_type.kind:
        case ResolvedTypeKind.TEXT:
            return "str"
        case ResolvedTypeKind.NUMBER:
            return "float"
        case ResolvedTypeKind.INTEGER:
            return "int"
        case ResolvedTypeKind.BOOLEAN:
            return "bool"
        case ResolvedTypeKind.DATE:
            imports.add("from datetime import date")
            return "date"
        case ResolvedTypeKind.DATETIME:
            imports.add("from datetime import datetime")
            return "datetime"
        case ResolvedTypeKind.LITERAL:
            imports.add("from typing import Literal")
            return f"Literal[{', '.join(repr(choice) for choice in resolved_type.choices or [])}]"
        case ResolvedTypeKind.CONCEPT:
            return _concept_annotation(resolved_type, by_ref=by_ref, imports=imports)
        case ResolvedTypeKind.LIST:
            item = _annotation(resolved_type.item, by_ref=by_ref, imports=imports) if resolved_type.item else any_annotation(imports=imports)
            return f"list[{item}]"
        case ResolvedTypeKind.DICT:
            value = _annotation(resolved_type.value, by_ref=by_ref, imports=imports) if resolved_type.value else any_annotation(imports=imports)
            return f"dict[str, {value}]"
        case ResolvedTypeKind.ANY:
            return any_annotation(imports=imports)


def _concept_annotation(resolved_type: ResolvedType, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    concept_ref = resolved_type.concept_ref
    if concept_ref is None:
        return any_annotation(imports=imports)
    concept = by_ref.get(concept_ref)
    if concept is not None:
        return python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
    return any_annotation(imports=imports)
