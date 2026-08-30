"""The reference projection: an input-form descriptor rendered as a fill-in inputs template.

This module is the **contract** the two shipped projections — the TypeScript helper in the `mthds`
package and its Python twin in `mthds-python` — must reproduce byte for byte. It exists in the dev
CLI, not in the runtime, because nothing in `pipelex` consumes it: its only job is to author the
expected bytes of the shared fixture corpus those two projections are pinned against.

**It walks the descriptor, never the runtime content classes**, and that is the whole difference
from the engine's own renderer (`pipelex/pipe_machinery/rendering/input_renderer.py`). The engine
reflects each input's pydantic class, so its template states what the *runtime* holds; this walks
the authored facts the descriptor states, so its template states what the *method declares*. The
two disagree in three places, deliberately, and the corpus records each one:

- **An optional structure field is rendered.** The engine passes `include_optional=False` at the top
  of an input's own class and not through the recursion, so it hides an optional field at depth one
  and shows one nested deeper. Every field the descriptor states is rendered here, at every depth.
- **A file-ish node is a leaf.** `native.Image` is `kind = "image"` in the descriptor — a leaf whose
  only fill-in value is a URL — while the engine expands `ImageContent` into its nine runtime
  fields, asking whoever fills the template in for a width and a mime type.
- **A fixed-count slot renders its count.** `Concept[N]` gets `N` elements; the engine emits one,
  which `InputShaper._shape_list` then rejects with `MultiplicityCountMismatchError`.

Two further rules are the descriptor's, not the engine's, because the engine has no equivalent:
an `enum` takes its first choice (the engine picks at random, which no committed template can
carry), and an `unknown` node renders as an empty object, the escape hatch's only honest value.

The match over `FieldKind` is exhaustive and carries no default arm on purpose: a kind added to the
standard breaks this generator where the rule for it has to be written, rather than falling through
to a guess.
"""

from typing import Any

from pipelex.core.pipes.variable_multiplicity import PresenceMarker, format_concept_with_multiplicity
from pipelex.pipeline.input_form import (
    FieldKind,
    InputFormField,
    InputFormItem,
    ListItem,
    PipeInputFormDescriptor,
)

MOCK_URL_PREFIX = "https://mock.invalid/"
FILE_CONTENT_KEY = "url"
TIME_FORMAT = "time"

# The single wire key a native scalar's value sits inside. It is a fact about the *payload*, which
# the descriptor deliberately does not carry — so the projection needs this table to build the
# explicit `{concept, content}` envelope. It is the standard's to state, not the runtime's: the
# native content shapes are pinned by `mthds/docs/spec/native-concepts.md`.
TEXT_CONTENT_KEY = "text"
NUMBER_CONTENT_KEY = "number"
BOOLEAN_CONTENT_KEY = "yes_no"
DATE_CONTENT_KEY = "date"
TIME_CONTENT_KEY = "time"

NATIVE_PREFIX = "native."

# The natives the runtime's input shaper cannot build top-down: their light form keeps the whole
# `{concept, content}` envelope, because a bare value at one of these positions is not re-shapable.
# The vocabulary is the standard's closed native set (`mthds/docs/spec/native-concepts.md`), which is
# why a projection may consult it: it reads an identity the descriptor states, never sniffs a shape.
OUT_OF_MATRIX_NATIVES = frozenset(
    {
        "Anything",
        "Composite",
        "Dynamic",
        "Html",
        "JSON",
        "Page",
        "SearchResult",
        "TextAndImages",
    }
)

# `native.Number`'s content is a number union, and the runtime placeholders it as `1` rather than as
# the `0` / `0.0` a plain `type = "number"` structure field takes. The descriptor states `kind =
# "number"` for both, so the native identity is what separates them.
NATIVE_NUMBER = "Number"
NATIVE_NUMBER_PLACEHOLDER = 1


def native_code(*, node: InputFormItem) -> str | None:
    """The native concept this node's chain names, if any.

    Reads `concept_ref` first, then the `refines` membership list, so a concept refining a native
    resolves the same way the native itself does.
    """
    candidates: list[str] = []
    if node.concept_ref is not None:
        candidates.append(node.concept_ref)
    if node.refines is not None:
        candidates.extend(node.refines)
    for candidate in candidates:
        if candidate.startswith(NATIVE_PREFIX):
            return candidate[len(NATIVE_PREFIX) :]
    return None


def keeps_envelope(*, node: InputFormItem) -> bool:
    """Whether this slot's light form keeps the ceremonial envelope instead of unwrapping.

    Two ways to earn it, and both mean the same thing — a bare value at this position is not
    re-shapable, so unwrapping would pin a template that does not run. Either the native is one the
    shaper cannot build top-down at all, or the descriptor states it as an object: the shaper's
    bare-value arm dispatches a native on its scalar kind, so it rejects the object outright.
    `native.Date` is the second case — it is a scalar the shaper knows, until the optional `time`
    beside its required `date` makes the rendered form an object.
    """
    code = native_code(node=node)
    if code is None:
        return False
    return code in OUT_OF_MATRIX_NATIVES or node.kind is FieldKind.OBJECT


def slot_content_key(*, node: InputFormItem) -> str | None:
    """The single wire key a slot-position scalar's value sits inside, or None when it is not one."""
    match node.kind:
        case FieldKind.TEXT | FieldKind.PROSE:
            if node.format == TIME_FORMAT:
                return TIME_CONTENT_KEY
            return TEXT_CONTENT_KEY
        case FieldKind.NUMBER:
            return NUMBER_CONTENT_KEY
        case FieldKind.BOOLEAN:
            return BOOLEAN_CONTENT_KEY
        case FieldKind.DATE:
            return DATE_CONTENT_KEY
        case FieldKind.ENUM:
            return TEXT_CONTENT_KEY
        case FieldKind.IMAGE | FieldKind.DOCUMENT:
            return FILE_CONTENT_KEY
        case FieldKind.OBJECT | FieldKind.LIST | FieldKind.UNKNOWN:
            return None


def _leaf_placeholder(*, node: InputFormItem, name: str) -> Any:
    """The fill-in value for a node the descriptor states as a leaf.

    `name` is the name of the field the value occupies, which is what the placeholder is built from:
    a structure field's own name when the leaf sits inside a content dict, and the content key when
    it sits at a slot, where the value occupies its native content class's single field.
    """
    match node.kind:
        case FieldKind.TEXT | FieldKind.PROSE:
            if node.format == TIME_FORMAT:
                return "12:00:00"
            return f"{name}_value"
        case FieldKind.DATE:
            if node.datetime:
                return "2026-01-01T12:00:00"
            return "2026-01-01"
        case FieldKind.NUMBER:
            if native_code(node=node) == NATIVE_NUMBER:
                return NATIVE_NUMBER_PLACEHOLDER
            if node.integer:
                return 0
            return 0.0
        case FieldKind.BOOLEAN:
            return False
        case FieldKind.ENUM:
            # The first choice, never a random one: these bytes are committed.
            if node.choices:
                return node.choices[0]
            return f"{name}_value"
        case FieldKind.IMAGE | FieldKind.DOCUMENT:
            return f"{MOCK_URL_PREFIX}{FILE_CONTENT_KEY}"
        case FieldKind.OBJECT | FieldKind.LIST | FieldKind.UNKNOWN:
            msg = f"Not a leaf kind: {node.kind}"
            raise ValueError(msg)


def _item_repetitions(*, node: ListItem) -> int:
    """How many elements a list renders: its declared count, or one example for a variable list."""
    return node.item_count if node.item_count is not None else 1


def project_value(*, node: InputFormItem, name: str) -> Any:
    """The value one descriptor node takes inside a content dict.

    A scalar-typed node is its bare placeholder; a concept-typed one (`image`, `document`, `object`)
    is the content dict its concept carries, because that is what sits at the field in the payload.

    One case reads as a scalar and is not: a nested node that names a native concept holds that
    native's own content object, not a bare value — `native.Text` inside a page's text-and-images is
    a `TextContent`, so the payload carries `{"text": ...}` there. The descriptor states the
    difference itself, in whether the node carries a `concept_ref`: an authored `type = "text"`
    structure field carries none and stays bare.
    """
    match node.kind:
        case FieldKind.TEXT | FieldKind.PROSE | FieldKind.DATE | FieldKind.NUMBER | FieldKind.BOOLEAN | FieldKind.ENUM:
            content_key = slot_content_key(node=node) if native_code(node=node) is not None else None
            if content_key is not None:
                return {content_key: _leaf_placeholder(node=node, name=content_key)}
            return _leaf_placeholder(node=node, name=name)
        case FieldKind.IMAGE | FieldKind.DOCUMENT:
            return {FILE_CONTENT_KEY: _leaf_placeholder(node=node, name=FILE_CONTENT_KEY)}
        case FieldKind.OBJECT:
            return {field.name: project_value(node=field, name=field.name) for field in node.fields}
        case FieldKind.LIST:
            item_value = project_value(node=node.item, name=f"{name}_item")
            return [item_value for _ in range(_item_repetitions(node=node))]
        case FieldKind.UNKNOWN:
            return {}


def _slot_content(*, node: InputFormItem, name: str) -> Any:
    """The `content` half of one slot's envelope — what the concept carries at that position."""
    content_key = slot_content_key(node=node)
    if content_key is not None:
        return {content_key: _leaf_placeholder(node=node, name=content_key)}
    match node.kind:
        case FieldKind.LIST:
            item_content = _slot_content(node=node.item, name=f"{name}_item")
            return [item_content for _ in range(_item_repetitions(node=node))]
        case (
            FieldKind.OBJECT
            | FieldKind.UNKNOWN
            | FieldKind.TEXT
            | FieldKind.PROSE
            | FieldKind.DATE
            | FieldKind.NUMBER
            | FieldKind.BOOLEAN
            | FieldKind.ENUM
            | FieldKind.IMAGE
            | FieldKind.DOCUMENT
        ):
            return project_value(node=node, name=name)


def _light_value(*, node: InputFormItem, name: str) -> Any:
    """One slot's (or one slot element's) light value: a scalar unwraps, everything else keeps its dict."""
    content_key = slot_content_key(node=node)
    if content_key is not None:
        return _leaf_placeholder(node=node, name=content_key)
    return project_value(node=node, name=name)


def _compact_slot(*, field: InputFormField) -> Any:
    """One slot in the light shape.

    An out-of-matrix native keeps the whole envelope, exactly as the runtime's own light rendering
    does: the shaper cannot rebuild those values from a bare one, so unwrapping would emit a
    template that no longer runs.
    """
    if keeps_envelope(node=field):
        return {"concept": field.concept_ref, "content": _slot_content(node=field, name=field.name)}
    match field.kind:
        case FieldKind.LIST:
            item_value = _light_value(node=field.item, name=f"{field.name}_item")
            return [item_value for _ in range(_item_repetitions(node=field))]
        case (
            FieldKind.OBJECT
            | FieldKind.UNKNOWN
            | FieldKind.TEXT
            | FieldKind.PROSE
            | FieldKind.DATE
            | FieldKind.NUMBER
            | FieldKind.BOOLEAN
            | FieldKind.ENUM
            | FieldKind.IMAGE
            | FieldKind.DOCUMENT
        ):
            return _light_value(node=field, name=field.name)


def slot_bundle_representation(*, field: InputFormField) -> str:
    """The `concept: …` comment text a light TOML template carries above each key.

    Rebuilt from the descriptor rather than from the pipe's `StuffSpec`, because that is all the
    shipped projections have: the concept ref, the multiplicity the `list` node states, and the
    presence marker.
    """
    presence = field.presence if field.presence is not None else PresenceMarker.PLAIN
    if isinstance(field, ListItem):
        multiplicity = field.item_count if field.item_count is not None else True
    else:
        multiplicity = None
    concept_ref = field.concept_ref if field.concept_ref is not None else ""
    return f"concept: {format_concept_with_multiplicity(concept_ref, multiplicity=multiplicity, presence=presence)}"


def project_inputs_template(*, descriptor: PipeInputFormDescriptor, explicit: bool) -> dict[str, Any]:
    """Project one pipe's descriptor into the fill-in inputs template.

    Args:
        descriptor: The pipe's input-form descriptor.
        explicit: When True, keep the ceremonial `{"concept", "content"}` envelope; when False
            (default shape), emit the light form a smart-inputs run accepts directly.

    Returns:
        The template, one entry per declared input slot, in authored order.
    """
    template: dict[str, Any] = {}
    for field in descriptor.fields:
        if explicit:
            template[field.name] = {
                "concept": field.concept_ref,
                "content": _slot_content(node=field, name=field.name),
            }
        else:
            template[field.name] = _compact_slot(field=field)
    return template


def project_concept_comments(*, descriptor: PipeInputFormDescriptor) -> dict[str, str]:
    """The per-slot `concept: …` comment map a light TOML rendering carries."""
    return {field.name: slot_bundle_representation(field=field) for field in descriptor.fields}
