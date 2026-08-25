"""Per-pipe input-form descriptors (`input_form`) for the validate surfaces.

This is the reference derivation of the MTHDS input-form descriptor (workspace spec
`docs/specs/mthds-input-form-descriptor.md`): for each loaded pipe, an ordered list of field
descriptors a renderer can turn into a fill-in form with no schema heuristics, no hardcoded
concept tables, and no description matching. It is keyed by the same namespaced `pipe_ref` set as
`pipe_io_contracts` — both are built from the same loaded pipes, so the key spaces are equal by
construction.

The descriptor is derived from **authored facts, never from the emitted JSON Schema**. Two fact
sources feed it:

- **Slot facts** come from the loaded pipes' `StuffSpec`s: authored input order, the three-valued
  presence marker (`plain` / `optional` / `force`), and the multiplicity including a fixed `[N]`
  count. `required` and `gating` are derived here, per the spec's stated rule.
- **Concept facts** come from the *qualified* library crate built from the parsed blueprints —
  qualified, not normalized, because normalization flattens in-crate refinement and the descriptor
  must report the `refines` chain as a list. Authored concepts contribute their description,
  refinement links and structure fields (defaults, choices, required-ness, nested concept refs —
  everything the schema projection loses); native concepts contribute their pinned blueprints;
  class-backed concepts (`structure = "ClassName"`) are reflected from the class registry.

The derivation is total: a node that cannot be mapped honestly reports `kind: "unknown"`, the
renderer's raw escape hatch against the sibling `json_schema`. Call it inside the validation
library's window, beside `build_pipe_io_contracts`: class-backed reflection reads the class
registry, and bundle-defined classes are only reliably current while their library is loaded.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen
from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer, model_validator
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from typing_extensions import Self

from pipelex.codegen.native_expansion import reflect_structure_class
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, fixed_item_count
from pipelex.interpreter_hub import get_current_library, get_library_manager
from pipelex.language.intent_hints import HintSiteValueKind, IntentWord, applicable_intent, merge_hints
from pipelex.libraries.crate_qualification import QualifiedCrateContent, qualify_crate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.system.registries.class_registry_access import get_class_registry


class FieldKind(StrEnum):
    """The closed `kind` union of the input-form descriptor — field intents, never widget names."""

    TEXT = "text"
    PROSE = "prose"
    DATE = "date"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    DOCUMENT = "document"
    IMAGE = "image"
    OBJECT = "object"
    LIST = "list"
    UNKNOWN = "unknown"

    @property
    def is_list(self) -> bool:
        match self:
            case FieldKind.LIST:
                return True
            case (
                FieldKind.TEXT
                | FieldKind.PROSE
                | FieldKind.DATE
                | FieldKind.NUMBER
                | FieldKind.BOOLEAN
                | FieldKind.ENUM
                | FieldKind.DOCUMENT
                | FieldKind.IMAGE
                | FieldKind.OBJECT
                | FieldKind.UNKNOWN
            ):
                return False


class InputFormField(BaseModel):
    """One field descriptor: a recursive node discriminated on `kind`.

    Every wire name is the spec's snake_case slot name. Inapplicable slots are dropped at
    serialization rather than emitted as JSON `null` — the report's valid arm is dumped without
    `exclude_none`, so the model owns its own wire shape. Applicable falsy values (`required: false`,
    `integer: false`, ...) are kept.
    """

    kind: FieldKind = Field(strict=False)
    name: str
    """The identifier as authored: the input slot name on a top-level field, the structure field
    name on a nested one. Unused on a `list`'s `item` (the index labels items)."""

    title: str | None = None
    """Human label; a renderer falls back to `name`. Never the generated class name."""

    concept_ref: str | None = None
    """The namespaced concept ref on every concept-typed node (`native.Document`, `demo.Invoice`).
    On a `list` node it names the ELEMENT concept."""

    refines: list[str] | None = None
    """The concept's refinement chain, immediate parent first, walked to its end. Absent when the
    concept refines nothing."""

    description: str | None = None
    required: bool
    """Top-level: the caller must supply the slot (`presence != "optional"`). Nested: the field must
    be present within the concept's payload. The two levels never interact."""

    presence: PresenceMarker | None = Field(default=None, strict=False)
    """The authored presence marker of the pipe's input slot, three-valued so `!` is not flattened.
    Top-level fields only."""

    gating: bool | None = None
    """Top-level fields only: the run cannot start until this slot has content. Stated rather than
    re-derived from `required` — a variable-multiplicity list never gates (`[]` is its legitimate
    value) while a fixed-count one does."""

    default_value: Any | None = None
    """The value applied when the caller omits the field — present only when a default was authored,
    never the emission's `null`-for-optional artifact. Always beside `required: false`: the blueprint
    rejects `required = true` with a default, and a reflected default makes the field not required."""

    examples: list[Any] | None = None
    hints: dict[str, str] | None = None
    """The node's effective MTHDS intent hints (spec: intent-hints.md): the key-by-key merge of the
    concept's refinement chain and the site's own hints, nearer/site layer winning. Flat
    string-to-string by contract. Everything well-formed rides here, unknown entries included; an
    applicable `intent` word additionally feeds `kind` (never competes with it)."""

    # `text` / `prose` constraint slots.
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    format: str | None = None
    # `date`: the `datetime` wire slot (the attribute name avoids shadowing the stdlib module).
    datetime_flag: bool | None = None
    # `number` slots.
    integer: bool | None = None
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: float | None = None
    exclusive_maximum: float | None = None
    # `enum`.
    choices: list[Any] | None = None
    # `object`.
    fields: list["InputFormField"] | None = None
    # `list`.
    item: "InputFormField | None" = None
    item_count: int | None = None
    """Present exactly when the slot was authored with a fixed `[N]` multiplicity."""

    @model_validator(mode="after")
    def validate_per_kind_slots(self) -> Self:
        match self.kind:
            case FieldKind.ENUM:
                if not self.choices:
                    msg = f"Field '{self.name}' of kind 'enum' must carry a non-empty 'choices' list"
                    raise ValueError(msg)
            case FieldKind.OBJECT:
                if self.fields is None:
                    msg = f"Field '{self.name}' of kind 'object' must carry 'fields'"
                    raise ValueError(msg)
            case FieldKind.LIST:
                if self.item is None:
                    msg = f"Field '{self.name}' of kind 'list' must carry 'item'"
                    raise ValueError(msg)
            case FieldKind.NUMBER:
                if self.integer is None:
                    msg = f"Field '{self.name}' of kind 'number' must state 'integer'"
                    raise ValueError(msg)
            case FieldKind.DATE:
                if self.datetime_flag is None:
                    msg = f"Field '{self.name}' of kind 'date' must state 'datetime'"
                    raise ValueError(msg)
            case FieldKind.TEXT | FieldKind.PROSE | FieldKind.BOOLEAN | FieldKind.DOCUMENT | FieldKind.IMAGE | FieldKind.UNKNOWN:
                pass
        return self

    @model_serializer(mode="wrap")
    def serialize_without_inapplicable_slots(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        dumped: dict[str, Any] = handler(self)
        wire = {slot: value for slot, value in dumped.items() if value is not None}
        if "datetime_flag" in wire:
            wire["datetime"] = wire.pop("datetime_flag")
        return wire


class PipeInputFormDescriptor(BaseModel):
    """The input form of one pipe — an `input_form` entry."""

    fields: list[InputFormField]
    """One field descriptor per input slot, in authored input order. Empty for a pipe with no inputs."""


def build_input_form(pipes: Sequence[PipeAbstract], *, qualified_crate: QualifiedCrateContent | None = None) -> dict[str, PipeInputFormDescriptor]:
    """Derive the `input_form` descriptors of loaded pipes from the authored blueprints of the current library.

    Works on any loaded `PipeAbstract`, `PipeSignature` placeholders included, iterating exactly
    as `build_pipe_io_contracts` does so the two artifacts share one key set. Must run while the
    validation library is still loaded (see the module docstring): the authored facts are the
    library's accumulated crate, which covers the validated bundle and every `library_dirs`
    bundle loaded beside it, so a concept from a library dir is derived exactly like a local one.

    Args:
        pipes: The loaded pipes to describe (typically `ValidateBundleResult.pipes`).
        qualified_crate: The current library's already-qualified crate, when the caller holds one.
            Qualification is a whole-crate walk, and a caller that runs several artifacts over the
            same window (the advisory-warnings collector) would otherwise pay for it twice. Omit it
            and the crate is read and qualified here, as before.

    Returns:
        `pipe_ref` → `PipeInputFormDescriptor` for every given pipe.
    """
    qualified = qualified_crate if qualified_crate is not None else qualify_current_library_crate()
    deriver = InputFormDeriver(concepts=qualified.concepts)
    input_form: dict[str, PipeInputFormDescriptor] = {}
    for pipe in pipes:
        # Slot hints come from the qualified blueprint, not the runtime spec: `StuffSpec` stays
        # hint-free by design (structural non-normativity). A pipe with no blueprint in the crate
        # (the fallback path) derives with no hints.
        blueprint = qualified.pipes.get(pipe.pipe_ref)
        blueprint_inputs: Mapping[str, str | InputSlotBlueprint] = blueprint.inputs if blueprint is not None and blueprint.inputs else {}
        fields = [
            deriver.derive_slot(name=var_name, stuff_spec=stuff_spec, slot_hints=_slot_hints_of(blueprint_inputs.get(var_name)))
            for var_name, stuff_spec in pipe.inputs.root.items()
        ]
        input_form[pipe.pipe_ref] = PipeInputFormDescriptor(fields=fields)
    return input_form


def qualify_current_library_crate() -> QualifiedCrateContent:
    """The current library's accumulated crate, qualified — empty when the library holds none.

    The single place that knows how to reach the authored facts of the open validation window, so
    the artifacts derived from them (the descriptors, the advisory lints) cannot read different
    facts. Requires a current library, like every other artifact built inside the window; a library
    that accumulated no blueprints yields an empty crate, from which every consumer derives nothing.
    """
    crate = get_library_manager().get_crate(library_id=get_current_library()) or LibraryCrateFactory.make_from_blueprints([])
    return qualify_crate(crate)


def _slot_hints_of(slot_value: "str | InputSlotBlueprint | None") -> dict[str, str] | None:
    """The authored hints of an input-slot value; only the expanded table form carries any."""
    return slot_value.hints if isinstance(slot_value, InputSlotBlueprint) else None


class InputFormDeriver:
    """Derives field descriptors over one qualified crate's concepts (`QualifiedCrateContent.concepts`)."""

    def __init__(self, *, concepts: dict[str, ConceptBlueprint | str]) -> None:
        self._concepts = concepts

    # ---- Pipe slots -------------------------------------------------------------------------------

    def derive_slot(self, *, name: str, stuff_spec: StuffSpec, slot_hints: dict[str, str] | None = None) -> InputFormField:
        """A top-level field: the concept node, list-wrapped when multiple, stamped with slot facts.

        `slot_hints` are the slot's authored hints from the qualified blueprint; the site-over-concept
        merge happens here (the concept node already carries the concept's effective hints).
        """
        node = self._concept_node(name=name, concept_ref=stuff_spec.concept.concept_ref, seen=frozenset())
        effective_hints = merge_hints([node.hints, slot_hints])
        if stuff_spec.is_multiple():
            item_count = fixed_item_count(multiplicity=stuff_spec.multiplicity)
            # A plural slot's merged hints ride the `list` node AND its `item` (the `concept_ref`
            # duplication precedent): applicability is judged per item, and a renderer reading
            # either node finds the same answer.
            node = InputFormField(
                kind=FieldKind.LIST,
                name=name,
                concept_ref=node.concept_ref,
                refines=node.refines,
                description=node.description,
                required=True,
                hints=effective_hints,
                item=_with_effective_hints(node=node, hints=effective_hints),
                item_count=item_count,
            )
        else:
            node = _with_effective_hints(node=node, hints=effective_hints)
        presence = stuff_spec.presence
        required = not presence.is_optional
        gating = required and not (node.kind.is_list and node.item_count is None)
        return node.model_copy(update={"presence": presence, "required": required, "gating": gating})

    # ---- Concept nodes ----------------------------------------------------------------------------

    def derive_concept(self, *, name: str, concept_ref: str) -> InputFormField:
        """The descriptor of a concept-typed node on its own, with no pipe-slot facts."""
        node = self._concept_node(name=name, concept_ref=concept_ref, seen=frozenset())
        return _with_effective_hints(node=node, hints=node.hints)

    def _concept_node(self, *, name: str, concept_ref: str, seen: frozenset[str]) -> InputFormField:
        """The descriptor of a concept-typed node (no slot facts); `seen` is the concept-ref path."""
        if concept_ref in seen:
            return _unknown_node(name=name, concept_ref=concept_ref)
        seen |= {concept_ref}
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
            native_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref)
            return self._native_node(name=name, native_code=_native_code_of(native_ref=native_ref), seen=seen)
        entry = self._concepts.get(concept_ref)
        if entry is None:
            # Not in the crate: no authored fact to read, so the honest answer is the raw escape hatch.
            return _unknown_node(name=name, concept_ref=concept_ref)
        if isinstance(entry, str):
            return _prose_promoted_node(name=name, concept_ref=concept_ref, description=entry, chain=[])
        return self._blueprint_node(name=name, concept_ref=concept_ref, blueprint=entry, seen=seen)

    def _blueprint_node(self, *, name: str, concept_ref: str, blueprint: ConceptBlueprint, seen: frozenset[str]) -> InputFormField:
        chain = self._refines_chain(concept_ref=concept_ref)
        node = self._blueprint_node_for_chain(name=name, concept_ref=concept_ref, blueprint=blueprint, chain=chain, seen=seen)
        # The concept's effective hints: its refinement chain merged nearer-wins, computed with the
        # same `_refines_chain` walk the structure merge uses. Carried on the node WITHOUT feeding
        # `kind` yet: this node may still receive a site layer (a slot's or a field's hints), and
        # the kind flip must read the final merge — see `_with_effective_hints` at the terminals.
        effective_hints = self._effective_hints(concept_ref=concept_ref, chain=chain)
        return node.model_copy(update={"hints": effective_hints}) if effective_hints else node

    def _effective_hints(self, *, concept_ref: str, chain: list[str]) -> dict[str, str] | None:
        """The concept's effective hints along its refinement chain (natives contribute nothing)."""
        layers: list[dict[str, str] | None] = []
        for ref in [*reversed(chain), concept_ref]:
            entry = self._concepts.get(ref)
            if isinstance(entry, ConceptBlueprint):
                layers.append(entry.hints)
        return merge_hints(layers)

    def _blueprint_node_for_chain(
        self, *, name: str, concept_ref: str, blueprint: ConceptBlueprint, chain: list[str], seen: frozenset[str]
    ) -> InputFormField:
        refines = chain or None
        merged_structure = self._merged_structure(concept_ref=concept_ref, chain=chain)
        if merged_structure is not None:
            fields = [self._structure_field(name=field_name, field=field, seen=seen) for field_name, field in merged_structure.items()]
            return InputFormField(
                kind=FieldKind.OBJECT,
                name=name,
                concept_ref=concept_ref,
                refines=refines,
                description=blueprint.description,
                required=True,
                fields=fields,
            )
        class_name = self._first_class_structure(concept_ref=concept_ref, chain=chain)
        if class_name is not None:
            return self._class_backed_node(
                name=name, concept_ref=concept_ref, class_name=class_name, description=blueprint.description, refines=refines, seen=seen
            )
        if chain and NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=chain[-1]):
            return self._native_node(
                name=name,
                native_code=_native_code_of(native_ref=chain[-1]),
                concept_ref=concept_ref,
                description=blueprint.description,
                refines=refines,
                seen=seen,
            )
        if chain and self._concepts.get(chain[-1]) is None:
            # The chain ends at a base this crate does not hold — a cross-package `alias->…` refines,
            # whose concepts live in an isolated child library and never enter the crate. The engine
            # backs such a concept with a field-less `StructuredContent` subclass, so its shape is
            # genuinely unknown: the same answer `_concept_node` gives for an absent concept.
            return _unknown_node(name=name, concept_ref=concept_ref, description=blueprint.description, refines=refines)
        return _prose_promoted_node(name=name, concept_ref=concept_ref, description=blueprint.description, chain=chain)

    def _native_node(
        self,
        *,
        name: str,
        native_code: NativeConceptCode,
        concept_ref: str | None = None,
        description: str | None = None,
        refines: list[str] | None = None,
        seen: frozenset[str],
    ) -> InputFormField:
        """The node of a native concept, or of a concept whose chain bottoms at one (identity-decided, never shape-sniffed)."""
        pinned = make_pinned_native_blueprint(native_code)
        kind: FieldKind
        integer: bool | None = None
        datetime_flag: bool | None = None
        text_format: str | None = None
        fields: list[InputFormField] | None = None
        match native_code:
            case NativeConceptCode.TEXT | NativeConceptCode.HTML:
                kind = FieldKind.PROSE
            case NativeConceptCode.NUMBER:
                kind = FieldKind.NUMBER
                integer = False
            case NativeConceptCode.YES_NO:
                kind = FieldKind.BOOLEAN
            case NativeConceptCode.DATE:
                kind = FieldKind.DATE
                datetime_flag = False
            case NativeConceptCode.TIME:
                kind = FieldKind.TEXT
                text_format = "time"
            case NativeConceptCode.DOCUMENT:
                kind = FieldKind.DOCUMENT
            case NativeConceptCode.IMAGE:
                kind = FieldKind.IMAGE
            case NativeConceptCode.PAGE | NativeConceptCode.TEXT_AND_IMAGES | NativeConceptCode.SEARCH_RESULT:
                kind = FieldKind.OBJECT
                pinned_structure = pinned.structure if isinstance(pinned.structure, dict) else {}
                fields = [self._structure_field(name=field_name, field=field, seen=seen) for field_name, field in pinned_structure.items()]
            case NativeConceptCode.DYNAMIC | NativeConceptCode.ANYTHING | NativeConceptCode.JSON | NativeConceptCode.COMPOSITE:
                kind = FieldKind.UNKNOWN
        return InputFormField(
            kind=kind,
            name=name,
            concept_ref=concept_ref or native_code.concept_ref,
            refines=refines,
            description=description or pinned.description,
            required=True,
            integer=integer,
            datetime_flag=datetime_flag,
            format=text_format,
            fields=fields,
        )

    def _class_backed_node(
        self,
        *,
        name: str,
        concept_ref: str,
        class_name: str,
        description: str | None,
        refines: list[str] | None,
        seen: frozenset[str],
    ) -> InputFormField:
        """A concept whose payload is stated by a registered class: a native class maps by identity, any other is reflected."""
        native_code = next((code for code in NativeConceptCode if code.structure_class_name == class_name), None)
        if native_code is not None:
            return self._native_node(name=name, native_code=native_code, concept_ref=concept_ref, description=description, refines=refines, seen=seen)
        structure_class = get_class_registry().get_class(name=class_name)
        if not (isinstance(structure_class, type) and issubclass(structure_class, BaseModel)):
            return _unknown_node(name=name, concept_ref=concept_ref, description=description, refines=refines)
        reflected = reflect_structure_class(structure_class=structure_class)
        if reflected is None:
            return _unknown_node(name=name, concept_ref=concept_ref, description=description, refines=refines)
        fields = [
            _with_reflected_constraints(
                node=self._structure_field(name=field_name, field=field, seen=seen), field_info=structure_class.model_fields[field_name]
            )
            for field_name, field in reflected.items()
        ]
        return InputFormField(
            kind=FieldKind.OBJECT, name=name, concept_ref=concept_ref, refines=refines, description=description, required=True, fields=fields
        )

    # ---- Crate walks ------------------------------------------------------------------------------

    def _refines_chain(self, *, concept_ref: str) -> list[str]:
        """The authored refinement links, immediate parent first, walked to the end (a native link ends it)."""
        chain: list[str] = []
        visited = {concept_ref}
        current = self._concepts.get(concept_ref)
        while isinstance(current, ConceptBlueprint) and current.refines:
            link = current.refines
            if link in visited:
                break
            chain.append(link)
            visited.add(link)
            if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=link):
                break
            current = self._concepts.get(link)
        return chain

    def _merged_structure(self, *, concept_ref: str, chain: list[str]) -> dict[str, ConceptStructureBlueprintType] | None:
        """The authored structure fields along the chain, base fields first, a refining concept overriding its parents'.

        `None` when no concept along the chain authors a structure table at all; `{}` when one does and
        that table is empty. The distinction is the engine's own: `ConceptFactory` branches on
        `structure is not None`, so an authored-but-empty table is backed by a field-less structured
        model with an empty object schema — not by `TextContent`. Testing truthiness here would report
        that concept as `prose` with a `native.Text` refines link nobody authored.
        """
        merged: dict[str, ConceptStructureBlueprintType] | None = None
        for ref in [*reversed(chain), concept_ref]:
            entry = self._concepts.get(ref)
            if isinstance(entry, ConceptBlueprint) and isinstance(entry.structure, dict):
                merged = {**(merged or {}), **entry.structure}
        return merged

    def _first_class_structure(self, *, concept_ref: str, chain: list[str]) -> str | None:
        for ref in [concept_ref, *chain]:
            entry = self._concepts.get(ref)
            if isinstance(entry, ConceptBlueprint) and isinstance(entry.structure, str):
                return entry.structure
        return None

    # ---- Structure fields -------------------------------------------------------------------------

    def _structure_field(self, *, name: str, field: ConceptStructureBlueprintType, seen: frozenset[str]) -> InputFormField:
        """A nested field from its structure blueprint: authored facts only, never slot facts.

        A field is a terminal hint site: the field's own hints merge over the referenced concept's
        effective hints (concept-typed and concept-item fields only — scalar fields have no concept
        layer), and the final merge is stamped here, feeding `kind` where applicable.
        """
        if isinstance(field, str):
            # The shorthand `field = "description"` form declares a required text field.
            return InputFormField(kind=FieldKind.TEXT, name=name, description=field, required=True)
        if field.choices:
            enum_node = InputFormField(
                kind=FieldKind.ENUM,
                name=name,
                description=field.description,
                required=field.required,
                choices=list(field.choices),
                default_value=field.default_value,
            )
            return _with_effective_hints(node=enum_node, hints=field.hints)
        match field.type:
            case ConceptStructureBlueprintFieldType.CONCEPT:
                if field.concept_ref is None:
                    return _unknown_node(name=name, description=field.description, required=field.required)
                node = self._concept_node(name=name, concept_ref=field.concept_ref, seen=seen)
                node = _with_effective_hints(node=node, hints=merge_hints([node.hints, field.hints]))
                return node.model_copy(update={"description": field.description, "required": field.required})
            case ConceptStructureBlueprintFieldType.LIST:
                item = self._list_item(name=name, field=field, seen=seen)
                # The merged hints ride the `list` node AND its `item` (the `concept_ref`
                # duplication precedent); a concept item already carries its concept layer.
                effective_hints = merge_hints([item.hints, field.hints])
                return InputFormField(
                    kind=FieldKind.LIST,
                    name=name,
                    concept_ref=item.concept_ref,
                    refines=item.refines,
                    description=field.description,
                    required=field.required,
                    default_value=field.default_value,
                    hints=effective_hints,
                    item=_with_effective_hints(node=item, hints=effective_hints),
                )
            case ConceptStructureBlueprintFieldType.DICT | None:
                unknown = _unknown_node(name=name, description=field.description, required=field.required, default_value=field.default_value)
                return _with_effective_hints(node=unknown, hints=field.hints)
            case (
                ConceptStructureBlueprintFieldType.TEXT
                | ConceptStructureBlueprintFieldType.INTEGER
                | ConceptStructureBlueprintFieldType.NUMBER
                | ConceptStructureBlueprintFieldType.BOOLEAN
                | ConceptStructureBlueprintFieldType.DATE
                | ConceptStructureBlueprintFieldType.DATETIME
                | ConceptStructureBlueprintFieldType.TIME
            ):
                scalar = _scalar_field(
                    field_type=field.type, name=name, description=field.description, required=field.required, default_value=field.default_value
                )
                return _with_effective_hints(node=scalar, hints=field.hints)

    def _list_item(self, *, name: str, field: ConceptStructureBlueprint, seen: frozenset[str]) -> InputFormField:
        """The element node of a list field; the inner type of a nested list is inexpressible in the blueprint."""
        item_type: ConceptStructureBlueprintFieldType | None
        try:
            item_type = ConceptStructureBlueprintFieldType(field.item_type) if field.item_type else None
        except ValueError:
            item_type = None
        match item_type:
            case ConceptStructureBlueprintFieldType.CONCEPT:
                if field.item_concept_ref is None:
                    return _unknown_node(name=name)
                return self._concept_node(name=name, concept_ref=field.item_concept_ref, seen=seen)
            case None | ConceptStructureBlueprintFieldType.LIST | ConceptStructureBlueprintFieldType.DICT:
                return _unknown_node(name=name)
            case (
                ConceptStructureBlueprintFieldType.TEXT
                | ConceptStructureBlueprintFieldType.INTEGER
                | ConceptStructureBlueprintFieldType.NUMBER
                | ConceptStructureBlueprintFieldType.BOOLEAN
                | ConceptStructureBlueprintFieldType.DATE
                | ConceptStructureBlueprintFieldType.DATETIME
                | ConceptStructureBlueprintFieldType.TIME
            ):
                return _scalar_field(field_type=item_type, name=name, required=True)


def _with_effective_hints(*, node: InputFormField, hints: dict[str, str] | None) -> InputFormField:
    """Stamp a node's FINAL effective hints; an applicable `intent` word feeds `kind`, never competes.

    Call exactly once per node, at the terminal where the full merge is known (slot, field, or bare
    concept). `node.kind` is still the no-hint default there, so an absent, unknown, or inapplicable
    intent leaves it untouched — and `rating` / `quantity` never change `kind` at all (both map to
    `number`; the union has no finer kind). Inapplicable and unknown content still rides the slot as
    preserved content (the advisory lint already warned).
    """
    if not hints:
        return node
    updates: dict[str, Any] = {"hints": hints}
    match applicable_intent(hints, site_kind=_node_site_kind(node)):
        case IntentWord.PROSE:
            updates["kind"] = FieldKind.PROSE
        case IntentWord.LABEL:
            updates["kind"] = FieldKind.TEXT
        case IntentWord.RATING | IntentWord.QUANTITY | None:
            pass
    return node.model_copy(update=updates)


def _node_site_kind(node: InputFormField) -> HintSiteValueKind:
    """The node's site value-kind for intent applicability (spec: intent-hints.md, Applicability).

    Recomputed from node facts, mirroring the lint's structural judgment (the known divergences are
    recorded in wip/engine-hints/deferred.md): `number` nodes come only from `integer`/`number`
    fields and `native.Number` chains, so the kind IS the judgment; `text`/`prose` nodes are
    text-valued EXCEPT a time-formatted text (`type = "time"` is neither) and an `Html`-backed node
    (`prose` presentation, but the chain reaches `native.Html`, not `native.Text`).
    """
    match node.kind:
        case FieldKind.NUMBER:
            return HintSiteValueKind.NUMBER_VALUED
        case FieldKind.TEXT | FieldKind.PROSE:
            if node.format is not None:
                return HintSiteValueKind.OTHER
            html_ref = NativeConceptCode.HTML.concept_ref
            if node.concept_ref == html_ref or (node.refines is not None and html_ref in node.refines):
                return HintSiteValueKind.OTHER
            return HintSiteValueKind.TEXT_VALUED
        case (
            FieldKind.DATE
            | FieldKind.BOOLEAN
            | FieldKind.ENUM
            | FieldKind.DOCUMENT
            | FieldKind.IMAGE
            | FieldKind.OBJECT
            | FieldKind.LIST
            | FieldKind.UNKNOWN
        ):
            return HintSiteValueKind.OTHER


def _scalar_field(
    *,
    field_type: ConceptStructureBlueprintFieldType,
    name: str,
    required: bool,
    description: str | None = None,
    default_value: Any | None = None,
) -> InputFormField:
    """The node of a scalar blueprint type: its kind and per-kind flags (a compound type maps to `unknown`)."""
    kind: FieldKind
    integer: bool | None = None
    datetime_flag: bool | None = None
    text_format: str | None = None
    match field_type:
        case ConceptStructureBlueprintFieldType.TEXT:
            kind = FieldKind.TEXT
        case ConceptStructureBlueprintFieldType.INTEGER:
            kind = FieldKind.NUMBER
            integer = True
        case ConceptStructureBlueprintFieldType.NUMBER:
            kind = FieldKind.NUMBER
            integer = False
        case ConceptStructureBlueprintFieldType.BOOLEAN:
            kind = FieldKind.BOOLEAN
        case ConceptStructureBlueprintFieldType.DATE:
            kind = FieldKind.DATE
            datetime_flag = False
        case ConceptStructureBlueprintFieldType.DATETIME:
            kind = FieldKind.DATE
            datetime_flag = True
        case ConceptStructureBlueprintFieldType.TIME:
            kind = FieldKind.TEXT
            text_format = "time"
        case ConceptStructureBlueprintFieldType.LIST | ConceptStructureBlueprintFieldType.DICT | ConceptStructureBlueprintFieldType.CONCEPT:
            kind = FieldKind.UNKNOWN
    return InputFormField(
        kind=kind,
        name=name,
        description=description,
        required=required,
        default_value=default_value,
        integer=integer,
        datetime_flag=datetime_flag,
        format=text_format,
    )


def _with_reflected_constraints(*, node: InputFormField, field_info: FieldInfo) -> InputFormField:
    """Stamp the facts a registered class states on a field: presence, default, and constraints.

    A pydantic default on a reflected class is an authored fact (the S2 ruling closing the D2
    deferral): the class author wrote it, validation applies it on absence exactly like a blueprint
    `default_value`, so `field_info.is_required()` is the source of truth for `required` and a
    defaulted field is never required — the same invariant the blueprint side enforces (E3). A
    `None` default is the emission artifact of optionality, never reported as a `default_value`.

    Constraint slots read only what applies to the node's kind: bounds on a `number`, length and
    pattern on a `text`. Anything else the class may declare is not a form fact and is left out.
    """
    constraints: dict[str, Any] = {}
    if field_info.is_required() != node.required:
        constraints["required"] = field_info.is_required()
    if field_info.default is not PydanticUndefined and field_info.default is not None:
        constraints["default_value"] = field_info.default
    match node.kind:
        case FieldKind.NUMBER:
            for constraint in field_info.metadata:
                match constraint:
                    case Gt(gt=bound):
                        constraints["exclusive_minimum"] = bound
                    case Ge(ge=bound):
                        constraints["minimum"] = bound
                    case Lt(lt=bound):
                        constraints["exclusive_maximum"] = bound
                    case Le(le=bound):
                        constraints["maximum"] = bound
                    case _:
                        pass
        case FieldKind.TEXT:
            for constraint in field_info.metadata:
                match constraint:
                    case MinLen(min_length=length):
                        constraints["min_length"] = length
                    case MaxLen(max_length=length):
                        constraints["max_length"] = length
                    case _:
                        # pydantic folds `pattern=` into its own general-metadata object.
                        pattern = getattr(constraint, "pattern", None)
                        if isinstance(pattern, str):
                            constraints["pattern"] = pattern
        case (
            FieldKind.PROSE
            | FieldKind.DATE
            | FieldKind.BOOLEAN
            | FieldKind.ENUM
            | FieldKind.DOCUMENT
            | FieldKind.IMAGE
            | FieldKind.OBJECT
            | FieldKind.LIST
            | FieldKind.UNKNOWN
        ):
            pass
    return node.model_copy(update=constraints) if constraints else node


def _prose_promoted_node(*, name: str, concept_ref: str, description: str, chain: list[str]) -> InputFormField:
    """A description-only or string-described concept: this engine backs it with a `TextContent` subclass."""
    return InputFormField(
        kind=FieldKind.PROSE,
        name=name,
        concept_ref=concept_ref,
        refines=[*chain, NativeConceptCode.TEXT.concept_ref],
        description=description,
        required=True,
    )


def _unknown_node(
    *,
    name: str,
    concept_ref: str | None = None,
    description: str | None = None,
    refines: list[str] | None = None,
    required: bool = True,
    default_value: Any | None = None,
) -> InputFormField:
    return InputFormField(
        kind=FieldKind.UNKNOWN,
        name=name,
        concept_ref=concept_ref,
        refines=refines,
        description=description,
        required=required,
        default_value=default_value,
    )


def _native_code_of(*, native_ref: str) -> NativeConceptCode:
    return NativeConceptCode(native_ref.rsplit(".", 1)[-1])
