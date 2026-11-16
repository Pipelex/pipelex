"""python-pydantic emitter: project a crate's concept set as plain `pydantic.BaseModel` types.

The neutral type projection — the same shapes as python-structures but with no Pipelex imports and
no `StructuredContent` base, so the generated module depends only on `pydantic` (and stdlib). Every
concept in the crate is emitted uniformly, including the materialized natives (`native.Text` becomes
a `Text` model), so the file is self-contained: a consumer needs the crate and pydantic, nothing else.

A concept reaching a native that may hold its value in storage (`Text`, `Markdown`, `Html`, `JSON`) is emitted
twice: its loaded shape under its own name, where such a native holds its value (`text: str`), and its wire shape
under the name with `Wire` appended, where it holds its value or the reference to it in storage. The wire shapes
follow every loaded class, so a reader finds the shape a client hands back first.

Modern typing throughout: builtin generics (`list` / `dict`), `X | None` for optionals, and
`from __future__ import annotations` so concept references resolve as forward names from the module.
"""

from pipelex.codegen.emitters.naming import allocate_python_class_names
from pipelex.codegen.emitters.python_common import (
    any_annotation,
    field_line,
    literal_annotation,
    order_by_base,
    python_header,
    python_module_body,
)
from pipelex.codegen.emitters.stored_value_shapes import wire_shape_note
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary
from pipelex.core.concepts.resolved_fields import ResolvedField, ResolvedType, ResolvedTypeKind
from pipelex.tools.misc.python_literals import class_docstring

_FILENAME = "models.py"


def emit_python_pydantic(library: ResolvedLibrary) -> list[EmittedFile]:
    """Emit the `models.py` module: one plain `BaseModel` per concept (natives included), then one per wire shape."""
    by_ref = library.by_ref()
    names_by_ref = allocate_python_class_names(library=library)
    in_module = set(by_ref)
    # A wire shape's base is a wire shape, never a loaded class, so each list orders within itself.
    ordered = order_by_base(library.concepts, in_module=in_module) + order_by_base(library.wire_shapes, in_module=in_module)

    # Every import is demand-driven — registered by the renderer that writes the name it imports.
    # Seeding the set up front would emit an unused import for the crate shapes that use neither
    # (all-opaque emits no field line; a fully-refining crate never reaches the `BaseModel` root),
    # and `ruff check --fix` deletes those, rewriting the body bytes and breaking the stamp.
    imports: set[str] = set()
    blocks = [_render_class(concept, by_ref=by_ref, names_by_ref=names_by_ref, imports=imports) for concept in ordered]

    body = python_module_body(header=python_header(target="python-pydantic"), imports=imports, blocks=blocks)
    return [EmittedFile(filename=_FILENAME, content=body)]


def _render_class(concept: ResolvedConcept, *, by_ref: dict[str, ResolvedConcept], names_by_ref: dict[str, str], imports: set[str]) -> str:
    class_name = names_by_ref[concept.concept_ref]
    base = _base_class(concept, names_by_ref=names_by_ref, imports=imports)
    extra_line: str | None
    if concept.wire_shape_of is not None:
        extra_line = wire_shape_note(loaded_name=names_by_ref[concept.wire_shape_of])
    elif concept.structureless and concept.imprecision_reason:
        extra_line = f"Imprecise: {concept.imprecision_reason}."
    else:
        extra_line = None
    docstring = class_docstring(concept.description, extra_line=extra_line)
    header = f"class {class_name}({base}):"
    if concept.structureless:
        # Opaque = pass-through, never lossy (B1-1): pydantic's default extra="ignore" would
        # silently strip every field on model_validate, so the unknown shape is kept verbatim.
        imports.add("from pydantic import ConfigDict")
        return f'{header}\n{docstring}\n\n    model_config = ConfigDict(extra="allow")'
    if not concept.fields:
        return f"{header}\n{docstring}"
    lines = [_render_field(concept_field, by_ref=by_ref, names_by_ref=names_by_ref, imports=imports) for concept_field in concept.fields]
    return f"{header}\n{docstring}\n\n" + "\n".join(lines)


def _base_class(concept: ResolvedConcept, *, names_by_ref: dict[str, str], imports: set[str]) -> str:
    if concept.base_ref is None:
        return _base_model(imports=imports)
    base_name = names_by_ref.get(concept.base_ref)
    if base_name is not None:
        return base_name
    # Cross-package / unknown base is not resolvable in-crate: fall back to a structurally valid root.
    return _base_model(imports=imports)


def _base_model(*, imports: set[str]) -> str:
    """The pydantic root base, registering its import — a concept refining an in-module concept never reaches it."""
    imports.add("from pydantic import BaseModel")
    return "BaseModel"


def _render_field(concept_field: ResolvedField, *, by_ref: dict[str, ResolvedConcept], names_by_ref: dict[str, str], imports: set[str]) -> str:
    annotation = _annotation(concept_field.resolved_type, by_ref=by_ref, names_by_ref=names_by_ref, imports=imports)
    # Only a field that may hold nothing is nullable: a defaulted field is never `None`, as in the runtime class.
    if concept_field.may_hold_nothing:
        annotation = f"{annotation} | None"
    return field_line(concept_field, annotation=annotation, imports=imports)


def _annotation(resolved_type: ResolvedType, *, by_ref: dict[str, ResolvedConcept], names_by_ref: dict[str, str], imports: set[str]) -> str:
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
            return _concept_annotation(resolved_type, by_ref=by_ref, names_by_ref=names_by_ref, imports=imports)
        case ResolvedTypeKind.LIST:
            item = (
                _annotation(resolved_type.item, by_ref=by_ref, names_by_ref=names_by_ref, imports=imports)
                if resolved_type.item
                else any_annotation(imports=imports)
            )
            return f"list[{item}]"
        case ResolvedTypeKind.DICT:
            value = (
                _annotation(resolved_type.value, by_ref=by_ref, names_by_ref=names_by_ref, imports=imports)
                if resolved_type.value
                else any_annotation(imports=imports)
            )
            return f"dict[str, {value}]"
        case ResolvedTypeKind.ANY:
            return any_annotation(imports=imports)


def _concept_annotation(resolved_type: ResolvedType, *, by_ref: dict[str, ResolvedConcept], names_by_ref: dict[str, str], imports: set[str]) -> str:
    concept_ref = resolved_type.concept_ref
    if concept_ref is None or concept_ref not in by_ref:
        return any_annotation(imports=imports)
    return names_by_ref[concept_ref]
