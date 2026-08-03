"""python-structures emitter: project a crate's concept set as Pipelex `StuffContent` classes.

The runtime idiom (today's `StructureGenerator` presentation) over the shared resolved layers. Each
non-native concept becomes a `StuffContent` subclass; native *references* map to the runtime content
classes (`TextContent`, ...); a concept that still refines a native inherits that content class, and
a structureless one inherits `TextContent` because that is what the runtime promotes it to (see
`_base_class`). Native concepts themselves are not re-emitted — they already exist in the runtime.

Field annotations use `from __future__ import annotations`, so concept references are plain forward
names resolved from the module namespace (no explicit string quoting, no ordering constraint beyond
class inheritance).

Modern typing throughout — builtin generics (`list` / `dict`) and `X | None` — matching both the
runtime `StructureGenerator` and the repo's Python standards. The emitted bytes are lint-clean on
arrival so a consumer's `ruff` run cannot invalidate the codegen stamp; see `render_import_block`.
"""

from pipelex.codegen.emitters.naming import python_class_name
from pipelex.codegen.emitters.python_common import (
    any_annotation,
    class_docstring,
    field_line,
    literal_annotation,
    order_by_base,
    python_header,
    python_module_body,
)
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.resolved_fields import ResolvedField, ResolvedType, ResolvedTypeKind
from pipelex.core.qualified_ref import QualifiedRef

_FILENAME = "structures.py"


def emit_python_structures(library: ResolvedLibrary) -> list[EmittedFile]:
    """Emit the `structures.py` module: one `StuffContent` subclass per non-native concept."""
    by_ref = library.by_ref()
    emitted = [concept for concept in library.concepts if not concept.is_native]
    in_module = {concept.concept_ref for concept in emitted}
    ordered = order_by_base(emitted, in_module=in_module)

    # Every import is demand-driven — registered by the renderer that writes the name it imports.
    # Seeding the set up front would emit an unused import for the crate shapes that use neither
    # (all-opaque, or every concept refining a native), and `ruff check --fix` deletes those.
    imports: set[str] = set()
    blocks = [_render_class(concept, by_ref=by_ref, imports=imports) for concept in ordered]

    body = python_module_body(header=python_header(target="python-structures"), imports=imports, blocks=blocks)
    return [EmittedFile(filename=_FILENAME, content=body)]


def _render_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    class_name = python_class_name(domain=concept.domain, code=concept.code, needs_qualification=concept.needs_qualification)
    base = _base_class(concept, by_ref=by_ref, imports=imports)
    caveat = f"Imprecise: {concept.imprecision_reason}." if concept.structureless and concept.imprecision_reason else None
    docstring = class_docstring(concept.description, extra_line=caveat)
    header = f"class {class_name}({base}):"
    if concept.structureless:
        # Opaque carries no declared field, so without this every field would hit pydantic's default
        # extra="ignore" and be silently stripped on model_validate (B1-1). It stays load-bearing on
        # all three structureless bases, `TextContent` included: there it preserves everything
        # *alongside* `text`. What it cannot do is make the promoted arm accept an object payload with
        # no `text` at all — that field is required, so pass-through holds for the fields around it,
        # not for a payload shaped like something else. The runtime's class for the same declaration is
        # a `TextContent` subclass too and refuses the same payload; see the exception noted in
        # docs/under-the-hood/codegen-projections.md.
        imports.add("from pydantic import ConfigDict")
        return f'{header}\n{docstring}\n\n    model_config = ConfigDict(extra="allow")'
    if not concept.fields:
        return f"{header}\n{docstring}"
    lines = [_render_field(concept_field, by_ref=by_ref, imports=imports) for concept_field in concept.fields]
    return f"{header}\n{docstring}\n\n" + "\n".join(lines)


def _base_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    if concept.base_ref is None:
        if concept.structureless and concept.opaque_python_class is None:
            # A concept declaring only a description is promoted by the runtime to a refinement of
            # native Text (`ConceptFactory._handle_basic_blueprint` generates it on a `TextContent`
            # base), so the projection has to land on the same content class. `TextContent` and
            # `StructuredContent` are siblings: emitting the latter makes the interpreter's
            # text-vs-object dispatch answer differently for the same authored concept, and the text
            # path's `model_validate({"text": ...})` succeeds on both, so nothing raises.
            # A Python-class-backed concept is the one structureless shape that keeps the root base:
            # its real shape lives in hand-written Python and is genuinely unknown here (B1-1 floor).
            return _native_class(NativeConceptCode.TEXT.concept_ref, imports=imports)
        return _structured_content(imports=imports)
    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept.base_ref):
        return _native_class(concept.base_ref, imports=imports)
    base = by_ref.get(concept.base_ref)
    if base is not None:
        return python_class_name(domain=base.domain, code=base.code, needs_qualification=base.needs_qualification)
    # Cross-package / unknown base is not resolvable in-crate: fall back to a structurally valid root.
    return _structured_content(imports=imports)


def _structured_content(*, imports: set[str]) -> str:
    """The runtime root base, registering its import — a concept whose content class is known uses `_native_class` instead."""
    imports.add("from pipelex.core.stuffs.structured_content import StructuredContent")
    return "StructuredContent"


def _render_field(concept_field: ResolvedField, *, by_ref: dict[str, ResolvedConcept], imports: set[str]) -> str:
    annotation = _annotation(concept_field.resolved_type, by_ref=by_ref, imports=imports)
    if not concept_field.required:
        annotation = f"{annotation} | None"
    return field_line(concept_field, annotation=annotation, imports=imports)


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
        case ResolvedTypeKind.TIME:
            imports.add("from datetime import time")
            return "time"
        case ResolvedTypeKind.LITERAL:
            return literal_annotation(choices=resolved_type.choices, imports=imports)
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
        # `Anything` alone has no content class of its own, so it falls back to the runtime root — via
        # the renderer that registers the import, never a bare name the module would not import.
        return _structured_content(imports=imports)
    imports.add(f"from {structure_class.__module__} import {structure_class.__name__}")
    return structure_class.__name__
