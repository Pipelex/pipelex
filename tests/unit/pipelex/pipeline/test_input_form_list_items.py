"""Unit-pin that a list's `item` lands on the standard's nameless layer, not the named one."""

from __future__ import annotations

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.pipeline.input_form import InputFormDeriver, ObjectItem, TextItem
from tests.helpers.input_form import as_list, as_object


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
