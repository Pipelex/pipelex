"""Unit-pin the deriver's escape hatches that the library loader keeps out of reach.

The loader rejects concept cycles (`LibraryLoadingError`) and a `structure = "ClassName"` naming an
unregistered class before a bundle ever reaches `build_input_form`, so those branches are exercised
directly on a hand-built qualified crate: the derivation must stay total and finite on any crate.
"""

from __future__ import annotations

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.pipeline.input_form import FieldKind, InputFormDeriver, ObjectItem, TextItem
from tests.helpers.input_form import as_list, as_object


def _concept_field(*, concept_ref: str) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description="link", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref=concept_ref)


class TestInputFormDeriverEscapeHatches:
    def test_cycle_guard_emits_unknown_on_revisit(self) -> None:
        """A concept path that revisits a ref stops at an `unknown` node carrying the ref — finite, never recursive."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Node": ConceptBlueprint(
                description="A node",
                structure={"label": "The label", "child": _concept_field(concept_ref="demo.Node")},
            ),
        }
        node = InputFormDeriver(concepts=concepts).derive_concept(name="root", concept_ref="demo.Node")

        child = as_object(node).fields[1]
        assert child.name == "child"
        assert child.kind == FieldKind.UNKNOWN
        assert child.concept_ref == "demo.Node"

    def test_indirect_cycle_is_cut_at_the_revisit(self) -> None:
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Left": ConceptBlueprint(description="Left", structure={"right": _concept_field(concept_ref="demo.Right")}),
            "demo.Right": ConceptBlueprint(description="Right", structure={"left": _concept_field(concept_ref="demo.Left")}),
        }
        left = InputFormDeriver(concepts=concepts).derive_concept(name="left", concept_ref="demo.Left")

        right = as_object(as_object(left).fields[0])
        assert right.fields[0].kind == FieldKind.UNKNOWN
        assert right.fields[0].concept_ref == "demo.Left"

    def test_unregistered_class_backed_concept_is_unknown(self) -> None:
        """With no class to reflect, the node keeps its identity and description and reports `unknown`."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Ghost": ConceptBlueprint(description="Backed by a class nobody registered", structure="NoSuchRegisteredClass"),
        }
        ghost = InputFormDeriver(concepts=concepts).derive_concept(name="ghost", concept_ref="demo.Ghost")

        assert ghost.kind == FieldKind.UNKNOWN
        assert ghost.concept_ref == "demo.Ghost"
        assert ghost.description == "Backed by a class nobody registered"

    def test_concept_absent_from_the_crate_is_unknown_without_a_class(self) -> None:
        """A slot typed with a concept the crate never saw (a `library_dirs` load) still gets a descriptor."""
        missing = InputFormDeriver(concepts={}).derive_concept(name="missing", concept_ref="elsewhere.Missing")

        assert missing.kind == FieldKind.UNKNOWN
        assert missing.concept_ref == "elsewhere.Missing"

    def test_chain_ending_at_a_base_absent_from_the_crate_is_unknown(self) -> None:
        """A cross-package `alias->…` base never enters the crate, so its shape is unknown — never prose."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.RefinedScore": ConceptBlueprint(description="Refines a dependency's score", refines="dep->other.Score"),
        }
        node = InputFormDeriver(concepts=concepts).derive_concept(name="score", concept_ref="demo.RefinedScore")

        assert node.kind == FieldKind.UNKNOWN
        assert node.refines == ["dep->other.Score"]
        assert node.description == "Refines a dependency's score"


class TestDerivedListItemsAreNameless:
    """A list's `item` lands on the standard's nameless layer, not on the named one wearing a blank name.

    Worth pinning explicitly, because every cheaper guard is blind to the difference. The wire is
    identical either way — the `item` slot is declared as the nameless model, so the serializer
    never writes a `name` whatever the object actually is — and a named model passes a static check
    against that slot too, since each `*Field` subclasses its `*Item`. So a node built one layer up
    and handed over unchanged (or one whose name was blanked with `model_copy`, which does not
    validate) would serialize correctly, type-check, and still be the wrong object. Only asking the
    derived item what it IS catches that.
    """

    def test_a_scalar_item_is_the_nameless_model(self) -> None:
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Post": ConceptBlueprint(
                description="A post",
                structure={
                    "tags": ConceptStructureBlueprint(
                        description="Its tags", type=ConceptStructureBlueprintFieldType.LIST, item_type=ConceptStructureBlueprintFieldType.TEXT
                    )
                },
            ),
        }
        post = InputFormDeriver(concepts=concepts).derive_concept(name="post", concept_ref="demo.Post")

        item = as_list(as_object(post).fields[0]).item
        assert isinstance(item, TextItem), f"Expected the nameless text model, got '{type(item).__name__}'"
        assert not hasattr(item, "name"), "An item carries no `name` member at all — not even one holding None"

    def test_a_concept_item_is_the_nameless_model_and_keeps_its_payload(self) -> None:
        """The rebuild drops the name and nothing else: the element concept's own fields survive it."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Gadget": ConceptBlueprint(description="A gadget", structure={"trinket": "Its trinket"}),
            "demo.Box": ConceptBlueprint(
                description="A box",
                structure={
                    "gadgets": ConceptStructureBlueprint(
                        description="Its gadgets",
                        type=ConceptStructureBlueprintFieldType.LIST,
                        item_type=ConceptStructureBlueprintFieldType.CONCEPT,
                        item_concept_ref="demo.Gadget",
                    )
                },
            ),
        }
        box = InputFormDeriver(concepts=concepts).derive_concept(name="box", concept_ref="demo.Box")

        item = as_list(as_object(box).fields[0]).item
        assert isinstance(item, ObjectItem), f"Expected the nameless object model, got '{type(item).__name__}'"
        assert not hasattr(item, "name")
        assert item.concept_ref == "demo.Gadget"
        assert [field.name for field in item.fields or []] == ["trinket"], "The element concept's payload rides through the rebuild"
