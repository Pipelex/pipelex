"""python-structures emitter: project a crate's concept set as Pipelex `StructuredContent` classes.

The runtime idiom (today's `StructureGenerator` presentation) over the shared resolved layers. Each
non-native concept becomes a `StructuredContent` subclass; native *references* map to the runtime
content classes (`TextContent`, ...); a concept that still refines a native inherits that content
class. Native concepts themselves are not re-emitted — they already exist in the runtime.

Field annotations use `from __future__ import annotations`, so concept references are plain forward
names resolved from the module namespace (no explicit string quoting, no ordering constraint beyond
class inheritance).
"""

from pipelex.codegen.emitters.naming import python_class_name
from pipelex.codegen.emitters.python_common import any_annotation, class_docstring, field_line, order_by_base, python_header
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary
from pipelex.codegen.resolved_fields import ResolvedField, ResolvedType, ResolvedTypeKind
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.qualified_ref import QualifiedRef

_FILENAME = "structures.py"


def emit_python_structures(library: ResolvedLibrary) -> list[EmittedFile]:
    """Emit the `structures.py` module: one `StructuredContent` subclass per non-native concept."""
    by_ref = library.by_ref()
    emitted = [concept for concept in library.concepts if not concept.is_native]
    in_module = {concept.concept_ref for concept in emitted}
    ordered = order_by_base(emitted, in_module=in_module)

    imports: set[str] = {"from pydantic import Field", "from pipelex.core.stuffs.structured_content import StructuredContent"}
    blocks = [_render_class(concept, by_ref=by_ref, imports=imports) for concept in ordered]

    header = python_header(target="python-structures")
    import_block = "\n".join(sorted(imports))
    body = f"{header}from __future__ import annotations\n\n{import_block}\n\n\n" + "\n\n\n".join(blocks) + "\n"
    return [EmittedFile(filename=_FILENAME, content=body)]


def _render_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    class_name = python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
    base = _base_class(concept, by_ref=by_ref, imports=imports)
    caveat = f"Imprecise: {concept.imprecision_reason}." if concept.structureless and concept.imprecision_reason else None
    docstring = class_docstring(concept.description, extra_line=caveat)
    header = f"class {class_name}({base}):"
    if not concept.fields:
        return f"{header}\n{docstring}"
    lines = [_render_field(concept_field, by_ref=by_ref, imports=imports) for concept_field in concept.fields]
    return f"{header}\n{docstring}\n\n" + "\n".join(lines)


def _base_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    if concept.base_ref is None:
        return "StructuredContent"
    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept.base_ref):
        return _native_class(concept.base_ref, imports=imports)
    base = by_ref.get(concept.base_ref)
    if base is not None:
        return python_class_name(domain=base.domain, code=base.code, needs_qualification=base.needs_qualification)
    # Cross-package / unknown base is not resolvable in-crate: fall back to a structurally valid root.
    return "StructuredContent"


def _render_field(concept_field: ResolvedField, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    annotation = _annotation(concept_field.resolved_type, by_ref=by_ref, imports=imports)
    if not concept_field.required:
        imports.add("from typing import Optional")
        annotation = f"Optional[{annotation}]"
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
            imports.add("from typing import List")
            item = _annotation(resolved_type.item, by_ref=by_ref, imports=imports) if resolved_type.item else any_annotation(imports=imports)
            return f"List[{item}]"
        case ResolvedTypeKind.DICT:
            imports.add("from typing import Dict")
            value = _annotation(resolved_type.value, by_ref=by_ref, imports=imports) if resolved_type.value else any_annotation(imports=imports)
            return f"Dict[str, {value}]"
        case ResolvedTypeKind.ANY:
            return any_annotation(imports=imports)


def _concept_annotation(resolved_type: ResolvedType, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    concept_ref = resolved_type.concept_ref
    if concept_ref is None:
        return any_annotation(imports=imports)
    if resolved_type.is_native:
        return _native_class(concept_ref, imports=imports)
    concept = by_ref.get(concept_ref)
    if concept is not None:
        return python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
    return any_annotation(imports=imports)


def _native_class(concept_ref: str, *, imports: set[str]) -> str:
    native_code = NativeConceptCode(QualifiedRef.parse(concept_ref).local_code)
    structure_class = native_code.structure_class
    if structure_class is None:
        return "StructuredContent"
    imports.add(f"from {structure_class.__module__} import {structure_class.__name__}")
    return structure_class.__name__
