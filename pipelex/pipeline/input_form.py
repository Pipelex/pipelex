"""Per-pipe input-form descriptors (`input_form`) for the validate surfaces.

This is the reference derivation of the MTHDS input-form descriptor (workspace spec
`docs/specs/mthds-input-form-descriptor.md`): for each loaded pipe, an ordered list of field
descriptors a renderer can turn into a fill-in form with no schema heuristics, no hardcoded
concept tables, and no description matching. It is keyed by the same namespaced `pipe_ref` set as
`pipe_io_contracts` — both are built from the same loaded pipes, so the key spaces are equal by
construction.

**The wire shapes belong to the standard, not to this engine.** `FieldKind`, the per-kind field
models, their two unions and `PipeInputFormDescriptor` are the models of
`mthds.protocol.input_form`, mirroring the standard's `input-form-descriptor` page; they are
imported and re-exported here so this module keeps its callers, and this engine holds no second
declaration of them. The union a node belongs to is decided by its position, not by its content:
every named position holds an `InputFormField`, while a `list`'s `item` holds the nameless
`InputFormItem`, whose per-kind models declare no `name` at all. What stays here is the
derivation: how an authored library becomes a descriptor. Because a node's kind IS its model, the deriver constructs the per-kind model rather
than passing a `kind`, and the models' own parse-time invariants — the closed shapes, the rule
that `presence` and `gating` are stated on every top-level field and nowhere below it, the rule
that a fixed `item_count` is at least two — gate this emission at derivation time rather than on
the wire.

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
from typing import Any, get_origin

from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen
from mthds.protocol.input_form import (
    BooleanField,
    BooleanItem,
    DateField,
    DateItem,
    DocumentField,
    DocumentItem,
    EnumField,
    EnumItem,
    FieldKind,
    ImageField,
    ImageItem,
    InputForm,
    InputFormField,
    InputFormItem,
    InputFormItemBase,
    ListField,
    ListItem,
    NumberField,
    NumberItem,
    ObjectField,
    ObjectItem,
    PipeInputFormDescriptor,
    ProseField,
    ProseItem,
    TextField,
    TextItem,
    TextValuedItemBase,
    UnknownField,
    UnknownItem,
)
from pydantic import BaseModel, TypeAdapter
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from pipelex.core.concepts.annotation_shapes import (
    is_number_union,
    is_union,
    list_item_annotation,
    native_code_for_content_class,
    scalar_field_type,
    strip_optional,
)
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import fixed_item_count
from pipelex.interpreter_hub import get_current_library, get_library_manager
from pipelex.language.intent_hints import HintSiteValueKind, IntentWord, applicable_intent, merge_hints
from pipelex.libraries.crate_qualification import QualifiedCrateContent, qualify_crate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.system.registries.class_registry_access import get_class_registry

__all__ = [
    "BooleanField",
    "BooleanItem",
    "DateField",
    "DateItem",
    "DocumentField",
    "DocumentItem",
    "EnumField",
    "EnumItem",
    "FieldKind",
    "ImageField",
    "ImageItem",
    "InputForm",
    "InputFormDeriver",
    "InputFormField",
    "InputFormItem",
    "InputFormItemBase",
    "ListField",
    "ListItem",
    "NumberField",
    "NumberItem",
    "ObjectField",
    "ObjectItem",
    "PipeInputFormDescriptor",
    "ProseField",
    "ProseItem",
    "TextField",
    "TextItem",
    "TextValuedItemBase",
    "UnknownField",
    "UnknownItem",
    "build_input_form",
    "qualify_current_library_crate",
]


def build_input_form(pipes: Sequence[PipeAbstract], *, qualified_crate: QualifiedCrateContent | None = None) -> InputForm:
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
    input_form: InputForm = {}
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
            node = ListField(
                name=name,
                concept_ref=node.concept_ref,
                refines=node.refines,
                description=node.description,
                required=True,
                hints=effective_hints,
                item=_as_list_item(node=_with_effective_hints(node=node, hints=effective_hints)),
                item_count=item_count,
            )
        else:
            node = _with_effective_hints(node=node, hints=effective_hints)
        presence = stuff_spec.presence
        required = not presence.is_optional
        gating = required and not (isinstance(node, ListField) and node.item_count is None)
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
            return ObjectField(
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
        node_ref = concept_ref or native_code.concept_ref
        text = description or pinned.description
        match native_code:
            case NativeConceptCode.TEXT:
                return ProseField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True)
            case NativeConceptCode.NUMBER:
                return NumberField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True, integer=False)
            case NativeConceptCode.YES_NO:
                return BooleanField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True)
            case NativeConceptCode.TIME:
                return TextField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True, format="time")
            case NativeConceptCode.DOCUMENT:
                return DocumentField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True)
            case NativeConceptCode.IMAGE:
                return ImageField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True)
            case (
                NativeConceptCode.DATE
                | NativeConceptCode.HTML
                | NativeConceptCode.PAGE
                | NativeConceptCode.TEXT_AND_IMAGES
                | NativeConceptCode.SEARCH_RESULT
            ):
                pinned_structure = pinned.structure if isinstance(pinned.structure, dict) else {}
                return ObjectField(
                    name=name,
                    concept_ref=node_ref,
                    refines=refines,
                    description=text,
                    required=True,
                    fields=[self._structure_field(name=field_name, field=field, seen=seen) for field_name, field in pinned_structure.items()],
                )
            case NativeConceptCode.DYNAMIC | NativeConceptCode.ANYTHING | NativeConceptCode.JSON | NativeConceptCode.COMPOSITE:
                return UnknownField(name=name, concept_ref=node_ref, refines=refines, description=text, required=True)

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
        return ObjectField(
            name=name,
            concept_ref=concept_ref,
            refines=refines,
            description=description,
            required=True,
            fields=self._reflected_class_fields(structure_class=structure_class, seen=seen, classes_seen=frozenset()),
        )

    # ---- Class reflection -------------------------------------------------------------------------

    def _reflected_class_fields(
        self, *, structure_class: type[BaseModel], seen: frozenset[str], classes_seen: frozenset[type[BaseModel]]
    ) -> list[InputFormField]:
        """One node per field the class declares, every annotation mapped on its own.

        Reflection here is **partial**, deliberately unlike the native consistency probe's
        faithful-or-absent rule (`native_expansion._reflect_structure_class`): an annotation with no
        honest node makes THAT field `unknown` and leaves its siblings stated. The two answers differ
        because the purposes do — the probe is compared against a normative pinned form,
        where a plausible-looking partial answer would be the failure, whereas the descriptor is
        total by contract. Collapsing the whole payload here hid every `document` and `image`
        position under a class that one sibling annotation happened to defeat, and a consumer
        preparing inputs from the descriptor would then pass a local file path through un-uploaded.

        A class declaring no field yields no nodes, and the `object` node built over them says so
        with an empty `fields` list: a payload that demands nothing — the class-backed twin of an
        empty authored structure table, not an opaque payload.
        """
        classes_seen |= {structure_class}
        return [
            _with_reflected_constraints(
                node=self._reflected_field(
                    name=field_name,
                    annotation=field_info.annotation,
                    description=field_info.description or field_name,
                    seen=seen,
                    classes_seen=classes_seen,
                ),
                field_info=field_info,
            )
            for field_name, field_info in structure_class.model_fields.items()
        ]

    def _reflected_field(
        self, *, name: str, annotation: Any, description: str, seen: frozenset[str], classes_seen: frozenset[type[BaseModel]]
    ) -> InputFormField:
        """One reflected field: the annotation's node, carrying the field's own description and optionality."""
        inner, required = strip_optional(annotation=annotation)
        node = self._reflected_node(name=name, annotation=inner, seen=seen, classes_seen=classes_seen)
        return node.model_copy(update={"description": description, "required": required})

    def _reflected_node(self, *, name: str, annotation: Any, seen: frozenset[str], classes_seen: frozenset[type[BaseModel]]) -> InputFormField:
        """The node one annotation maps to, before the field's own facts are stamped on it.

        The shape questions are the blueprint reflection's own (`core/concepts/annotation_shapes.py`),
        answered in descriptor terms: a native content class is that native's node — routed through
        `_concept_node`, so the concept cycle guard covers a pinned native's own fields — a nested
        non-native model is an `object` whose fields are reflected in turn, which is what keeps a
        file-bearing field one level down visible, and an annotation with no honest node is `unknown`.
        """
        if is_number_union(annotation=annotation):
            return NumberField(name=name, required=True, integer=False)
        if is_union(annotation=annotation):
            # A union that is neither `X | None` (already peeled) nor a number union has no single node shape.
            return _unknown_node(name=name)
        origin = get_origin(annotation)
        if origin is list:
            return self._reflected_list_node(name=name, annotation=annotation, seen=seen, classes_seen=classes_seen)
        if origin is dict:
            # A mapping with unspecified value types, exactly as a `dict` structure field reports.
            return _unknown_node(name=name)
        scalar_type = scalar_field_type(annotation=annotation)
        if scalar_type is not None:
            return _scalar_field(field_type=scalar_type, name=name, required=True)
        native_code = native_code_for_content_class(annotation=annotation)
        if native_code is not None:
            return self._concept_node(name=name, concept_ref=native_code.concept_ref, seen=seen)
        if isinstance(annotation, type) and issubclass(annotation, BaseModel) and annotation not in classes_seen:
            # A nested model already on the path would recurse forever; the revisit is `unknown`,
            # the same answer the concept walk gives a concept ref it has already seen.
            return ObjectField(
                name=name, required=True, fields=self._reflected_class_fields(structure_class=annotation, seen=seen, classes_seen=classes_seen)
            )
        return _unknown_node(name=name)

    def _reflected_list_node(self, *, name: str, annotation: Any, seen: frozenset[str], classes_seen: frozenset[type[BaseModel]]) -> InputFormField:
        """A reflected `list[X]`: the element node derived one layer down and carried in `item`."""
        item_annotation = list_item_annotation(annotation=annotation)
        item = (
            _unknown_node(name=name)
            if item_annotation is None
            else self._reflected_node(name=name, annotation=item_annotation, seen=seen, classes_seen=classes_seen)
        )
        return ListField(name=name, concept_ref=item.concept_ref, refines=item.refines, required=True, item=_as_list_item(node=item))

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
        that concept as `prose`, contradicting the object schema the engine emits beside it.
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
            return TextField(name=name, description=field, required=True)
        if field.choices:
            enum_node = EnumField(
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
                return ListField(
                    name=name,
                    concept_ref=item.concept_ref,
                    refines=item.refines,
                    description=field.description,
                    required=field.required,
                    default_value=field.default_value,
                    hints=effective_hints,
                    item=_as_list_item(node=_with_effective_hints(node=item, hints=effective_hints)),
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


_LIST_ITEM_ADAPTER: TypeAdapter[InputFormItem] = TypeAdapter(InputFormItem)
"""Parses a node's slots into its nameless counterpart, picked by the union's own `kind` discriminator.

Going through the union rather than a kind-to-model table here keeps the standard's kind list in
one place: a kind added upstream lands in `InputFormItem` and needs no entry on this side.
"""


def _as_list_item(*, node: InputFormField) -> InputFormItem:
    """A node in `item` position: a list's `item` has no authored name and carries no `name` member.

    The spec states the absence outright (the index labels items, and a sentinel would be a value
    two producers could pick differently), and the standard makes it structural — the two layers
    are separate unions, and none of the item models declares `name`. So the element node derived
    under the list's own name is rebuilt one layer down from the same slots, rather than having its
    name blanked: `model_copy(update=...)` does not validate, and blanking would leave a required
    `str` slot holding `None` — right on the wire, wrong on the type, and unnoticed at runtime.
    """
    return _LIST_ITEM_ADAPTER.validate_python({slot: value for slot, value in node if slot != "name"})


def _with_effective_hints(*, node: InputFormField, hints: dict[str, str] | None) -> InputFormField:
    """Stamp a node's FINAL effective hints; an applicable `intent` word feeds `kind`, never competes.

    Call exactly once per node, at the terminal where the full merge is known (slot, field, or bare
    concept). The node is still on its no-hint default kind there, so an absent, unknown, or
    inapplicable intent leaves it untouched — and `rating` / `quantity` never change the kind at all
    (both map to `number`; the union has no finer kind). Inapplicable and unknown content still rides
    the slot as preserved content (the advisory lint already warned).
    """
    if not hints:
        return node
    match applicable_intent(hints, site_kind=_node_site_kind(node)):
        case IntentWord.PROSE:
            return _recast_text_kind(node=node, hints=hints, to_prose=True)
        case IntentWord.LABEL:
            return _recast_text_kind(node=node, hints=hints, to_prose=False)
        case IntentWord.RATING | IntentWord.QUANTITY | None:
            return node.model_copy(update={"hints": hints})


def _recast_text_kind(*, node: InputFormField, hints: dict[str, str], to_prose: bool) -> InputFormField:
    """Rebuild a text-valued node as the kind an intent word asks for, carrying its slots across.

    A node's kind IS its model since the shapes came from the standard, so flipping `text` to `prose`
    (or back) is a rebuild rather than a field update. Only a text-valued site reaches here — `prose`
    and `label` apply nowhere else — so the source is always a `text` or `prose` node and its own
    extra slots are the shared text constraints, which carry over unchanged.
    """
    if not isinstance(node, TextValuedItemBase):
        # Unreachable while `_node_site_kind` reports text-valued for the text kinds alone; stated
        # rather than asserted, so a future kind that reports text-valued degrades to a hint stamp.
        return node.model_copy(update={"hints": hints})
    kind_model = ProseField if to_prose else TextField
    return kind_model(
        name=node.name,
        title=node.title,
        concept_ref=node.concept_ref,
        refines=node.refines,
        description=node.description,
        required=node.required,
        presence=node.presence,
        gating=node.gating,
        default_value=node.default_value,
        examples=node.examples,
        hints=hints,
        min_length=node.min_length,
        max_length=node.max_length,
        pattern=node.pattern,
        format=node.format,
    )


def _node_site_kind(node: InputFormField) -> HintSiteValueKind:
    """The node's site value-kind for intent applicability (spec: intent-hints.md, Applicability).

    Recomputed from node facts, mirroring the lint's structural judgment (the known divergences are
    recorded in wip/engine-hints/deferred.md): `number` nodes come only from `integer`/`number`
    fields and `native.Number` chains, so the kind IS the judgment; `text`/`prose` nodes are
    text-valued EXCEPT a time-formatted text (`type = "time"` is neither). A `native.Html` chain
    derives an `object` node since the standard put it on the object arm, so it never reaches the
    text-valued case.
    """
    match node:
        case NumberField():
            return HintSiteValueKind.NUMBER_VALUED
        case TextField() | ProseField():
            if node.format is not None:
                return HintSiteValueKind.OTHER
            return HintSiteValueKind.TEXT_VALUED
        case DateField() | BooleanField() | EnumField() | DocumentField() | ImageField() | ObjectField() | ListField() | UnknownField():
            return HintSiteValueKind.OTHER


def _scalar_field(
    *,
    field_type: ConceptStructureBlueprintFieldType,
    name: str,
    required: bool,
    description: str | None = None,
    default_value: Any | None = None,
) -> InputFormField:
    """The node of a scalar blueprint type: its kind and per-kind slots (a compound type maps to `unknown`)."""
    match field_type:
        case ConceptStructureBlueprintFieldType.TEXT:
            return TextField(name=name, description=description, required=required, default_value=default_value)
        case ConceptStructureBlueprintFieldType.INTEGER:
            return NumberField(name=name, description=description, required=required, default_value=default_value, integer=True)
        case ConceptStructureBlueprintFieldType.NUMBER:
            return NumberField(name=name, description=description, required=required, default_value=default_value, integer=False)
        case ConceptStructureBlueprintFieldType.BOOLEAN:
            return BooleanField(name=name, description=description, required=required, default_value=default_value)
        case ConceptStructureBlueprintFieldType.DATE:
            return DateField(name=name, description=description, required=required, default_value=default_value, datetime=False)
        case ConceptStructureBlueprintFieldType.DATETIME:
            return DateField(name=name, description=description, required=required, default_value=default_value, datetime=True)
        case ConceptStructureBlueprintFieldType.TIME:
            return TextField(name=name, description=description, required=required, default_value=default_value, format="time")
        case ConceptStructureBlueprintFieldType.LIST | ConceptStructureBlueprintFieldType.DICT | ConceptStructureBlueprintFieldType.CONCEPT:
            return UnknownField(name=name, description=description, required=required, default_value=default_value)


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
    match node:
        case NumberField():
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
        case TextField():
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
            ProseField() | DateField() | BooleanField() | EnumField() | DocumentField() | ImageField() | ObjectField() | ListField() | UnknownField()
        ):
            pass
    return node.model_copy(update=constraints) if constraints else node


def _prose_promoted_node(*, name: str, concept_ref: str, description: str, chain: list[str]) -> InputFormField:
    """A description-only or string-described concept: this engine backs it with a `TextContent` subclass.

    `refines` is the authored chain alone, terminating wherever it actually terminates — the spec
    forbids reconstructing links the producer does not hold, so no `native.Text` link is appended.
    Text-valuedness reaches the wire as `kind: "prose"`.
    """
    return ProseField(
        name=name,
        concept_ref=concept_ref,
        refines=chain or None,
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
    return UnknownField(
        name=name,
        concept_ref=concept_ref,
        refines=refines,
        description=description,
        required=required,
        default_value=default_value,
    )


def _native_code_of(*, native_ref: str) -> NativeConceptCode:
    return NativeConceptCode(native_ref.rsplit(".", 1)[-1])
