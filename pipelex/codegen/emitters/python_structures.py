"""python-structures emitter: project a crate's concept set as Pipelex `StuffContent` classes.

The runtime idiom, as source: the class `StructureGenerator` builds from data at load, over the shared resolved layers. Each
non-native concept becomes a `StuffContent` subclass; native *references* map to the runtime content
classes (`TextContent`, ...); a concept that still refines a native inherits that content class, and
a structureless one inherits `TextContent` because that is what the runtime promotes it to (see
`_base_class`). Native concepts themselves are not re-emitted — they already exist in the runtime.

Field annotations use `from __future__ import annotations`, so concept references are plain forward
names resolved from the module namespace (no explicit string quoting, no ordering constraint beyond
class inheritance).

Modern typing throughout — builtin generics (`list` / `dict`) and `X | None` — matching the repo's
Python standards. The emitted bytes are lint-clean on
arrival so a consumer's `ruff` run cannot invalidate the codegen stamp; see `render_import_block`.
"""

from datetime import date, datetime, time
from typing import Any, cast

from pipelex.codegen.emitters.naming import python_class_name
from pipelex.codegen.emitters.python_common import (
    PY_EXPLODE_WIDTH,
    any_annotation,
    field_line,
    format_default_value,
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
from pipelex.tools.misc.python_literals import class_docstring

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
    if concept_field.contract_facts:
        return field_line(
            concept_field,
            annotation=_constrained(annotation=annotation, concept_field=concept_field, imports=imports),
            imports=imports,
        )
    # Only a field that may hold nothing is nullable: a defaulted field is never `None`, as in the runtime class.
    if concept_field.may_hold_nothing:
        annotation = f"{annotation} | None"
    return field_line(concept_field, annotation=annotation, imports=imports)


def _constrained(*, annotation: str, concept_field: ResolvedField, imports: set[str]) -> str:
    """The annotation carrying the field's contract facts, which the runtime class enforces and states alike (`ContractFacts`),
    `| None` included when the field may hold nothing.

    A field typed by a concept is marked `carried`, since its facts constrain the value its concept carries. The facts are
    authored values, rendered as literals (`format_default_value`). Flat when the field's head fits `PY_EXPLODE_WIDTH`, as
    `field_line` leaves a flat annotation; otherwise in the exploded form `ruff format` writes, a magic trailing comma
    closing every bracket, so no consumer's line length rewraps it.
    """
    imports.add("from typing import Annotated")
    imports.add("from pipelex.core.concepts.contract_fact_projection import ContractFacts")
    _register_temporal_imports(value=concept_field.contract_facts, imports=imports)
    facts = {format_default_value(key): format_default_value(value) for key, value in sorted(concept_field.contract_facts.items())}
    carried = concept_field.resolved_type.kind.is_concept
    may_hold_nothing = concept_field.may_hold_nothing
    flat_entries = ", ".join(f"{key}: {value}" for key, value in facts.items())
    flat = f"Annotated[{annotation}, ContractFacts({{{flat_entries}}}{', carried=True' if carried else ''})]"
    if may_hold_nothing:
        flat = f"{flat} | None"
    if len(flat) <= PY_EXPLODE_WIDTH - len(f"    {concept_field.name}: ") - len(" = Field("):
        return flat
    depth = 2 if may_hold_nothing else 1
    lines = ["Annotated[", f"{_indent(depth=depth + 1)}{annotation},", f"{_indent(depth=depth + 1)}ContractFacts(", f"{_indent(depth=depth + 2)}{{"]
    for key, value in sorted(concept_field.contract_facts.items()):
        lines.extend(_exploded_entry(key=format_default_value(key), value=value, depth=depth + 3))
    lines.append(f"{_indent(depth=depth + 2)}}},")
    if carried:
        lines.append(f"{_indent(depth=depth + 2)}carried=True,")
    lines.extend((f"{_indent(depth=depth + 1)}),", f"{_indent(depth=depth)}]"))
    exploded = "\n".join(lines)
    if not may_hold_nothing:
        return exploded
    return f"(\n{_indent(depth=2)}{exploded}\n{_indent(depth=2)}| None\n{_indent(depth=1)})"


def _indent(*, depth: int) -> str:
    return "    " * depth


def _exploded_entry(*, key: str, value: Any, depth: int) -> list[str]:
    """One entry of an exploded facts table: flat, but a list exploded with a magic trailing comma, as `examples` may run long."""
    if isinstance(value, list):
        items = [f"{_indent(depth=depth + 1)}{format_default_value(item)}," for item in cast("list[Any]", value)]
        return [f"{_indent(depth=depth)}{key}: [", *items, f"{_indent(depth=depth)}],"]
    return [f"{_indent(depth=depth)}{key}: {format_default_value(value)},"]


def _register_temporal_imports(*, value: Any, imports: set[str]) -> None:
    """Register the `datetime` names `format_default_value` spells a date, a date-time or a time of `value` with."""
    if isinstance(value, datetime):
        imports.add("from datetime import datetime")
    elif isinstance(value, date):
        imports.add("from datetime import date")
    elif isinstance(value, time):
        imports.add("from datetime import time")
    elif isinstance(value, list):
        for item in cast("list[Any]", value):
            _register_temporal_imports(value=item, imports=imports)
    elif isinstance(value, dict):
        for item in cast("dict[Any, Any]", value).values():
            _register_temporal_imports(value=item, imports=imports)


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
