"""Hints on the input-form descriptor (spec: intent-hints.md + mthds-input-form-descriptor.md):
effective merges visible on the wire, intent feeding `kind` on applicable sites only, list/item
duplication, and preserved-content riding.
"""

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.pipeline.input_form import FieldKind, InputFormDeriver

_CONCEPTS: dict[str, ConceptBlueprint | str] = {
    # Description-only concept: text-valued, no-hint kind is `prose`.
    "docs.Essay": ConceptBlueprint(description="an essay", hints={"intent": "prose"}),
    "docs.Title": ConceptBlueprint(description="a title", hints={"intent": "label"}),
    # Chain: base declares label, refiner overrides with prose; a second refiner inherits.
    "docs.Badge": ConceptBlueprint(description="a badge", hints={"intent": "label", "emphasis": "base"}),
    "docs.SpecialBadge": ConceptBlueprint(description="a special badge", refines="docs.Badge", hints={"intent": "prose"}),
    "docs.PlainBadge": ConceptBlueprint(description="a plain badge", refines="docs.Badge"),
    # Number-valued chain.
    "docs.Score": ConceptBlueprint(description="a score", refines="native.Number", hints={"intent": "rating"}),
    # Structured concept: neither text- nor number-valued.
    "docs.Card": ConceptBlueprint(
        description="a card",
        structure={
            "title": ConceptStructureBlueprint(description="the title", type=ConceptStructureBlueprintFieldType.TEXT, hints={"intent": "label"}),
            "body": ConceptStructureBlueprint(description="the body", type=ConceptStructureBlueprintFieldType.TEXT),
            "stars": ConceptStructureBlueprint(description="the stars", type=ConceptStructureBlueprintFieldType.INTEGER, hints={"intent": "rating"}),
            "essay": ConceptStructureBlueprint(
                description="the essay", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="docs.Essay", hints={"intent": "label"}
            ),
            "tags": ConceptStructureBlueprint(
                description="the tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", hints={"intent": "label"}
            ),
        },
        hints={"intent": "prose"},
    ),
}


def _deriver() -> InputFormDeriver:
    return InputFormDeriver(concepts=dict(_CONCEPTS))


class TestConceptEffectiveHints:
    def test_prose_intent_keeps_prose_kind(self):
        node = _deriver().derive_concept(name="essay", concept_ref="docs.Essay")
        assert node.kind is FieldKind.PROSE
        assert node.hints == {"intent": "prose"}

    def test_label_intent_flips_text_valued_node_to_text(self):
        node = _deriver().derive_concept(name="title", concept_ref="docs.Title")
        assert node.kind is FieldKind.TEXT
        assert node.hints == {"intent": "label"}

    def test_chain_override_nearer_wins_key_by_key(self):
        node = _deriver().derive_concept(name="badge", concept_ref="docs.SpecialBadge")
        # Own `intent` wins; `emphasis` inherited, not cleared.
        assert node.hints == {"intent": "prose", "emphasis": "base"}
        assert node.kind is FieldKind.PROSE

    def test_hintless_refiner_inherits_effective_hints(self):
        node = _deriver().derive_concept(name="badge", concept_ref="docs.PlainBadge")
        assert node.hints == {"intent": "label", "emphasis": "base"}
        assert node.kind is FieldKind.TEXT

    def test_rating_on_number_valued_node_rides_without_changing_kind(self):
        node = _deriver().derive_concept(name="score", concept_ref="docs.Score")
        assert node.kind is FieldKind.NUMBER
        assert node.hints == {"intent": "rating"}

    def test_inapplicable_intent_on_object_rides_without_changing_kind(self):
        node = _deriver().derive_concept(name="card", concept_ref="docs.Card")
        assert node.kind is FieldKind.OBJECT
        assert node.hints == {"intent": "prose"}


class TestStructureFieldHints:
    def test_field_hints_stamped_and_feed_kind(self):
        card = _deriver().derive_concept(name="card", concept_ref="docs.Card")
        fields = {field.name: field for field in card.fields or []}
        assert fields["title"].kind is FieldKind.TEXT
        assert fields["title"].hints == {"intent": "label"}
        assert fields["body"].hints is None
        assert fields["body"].kind is FieldKind.TEXT

    def test_rating_on_integer_field_rides_without_changing_kind(self):
        card = _deriver().derive_concept(name="card", concept_ref="docs.Card")
        fields = {field.name: field for field in card.fields or []}
        assert fields["stars"].kind is FieldKind.NUMBER
        assert fields["stars"].integer is True
        assert fields["stars"].hints == {"intent": "rating"}

    def test_concept_typed_field_site_wins_over_concept_layer(self):
        card = _deriver().derive_concept(name="card", concept_ref="docs.Card")
        fields = {field.name: field for field in card.fields or []}
        # Essay's concept layer says prose; the field site says label — the site wins.
        assert fields["essay"].hints == {"intent": "label"}
        assert fields["essay"].kind is FieldKind.TEXT

    def test_list_field_hints_ride_list_and_item(self):
        card = _deriver().derive_concept(name="card", concept_ref="docs.Card")
        fields = {field.name: field for field in card.fields or []}
        tags = fields["tags"]
        assert tags.kind is FieldKind.LIST
        assert tags.hints == {"intent": "label"}
        assert tags.item is not None
        assert tags.item.hints == {"intent": "label"}
        # The item is the text-valued site: the label intent flips ITS kind.
        assert tags.item.kind is FieldKind.TEXT


class TestHintFreeByteIdentity:
    def test_hint_free_derivation_carries_no_hints_key(self):
        concepts: dict[str, ConceptBlueprint | str] = {
            "docs.Plain": ConceptBlueprint(
                description="plain",
                structure={"note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.TEXT)},
            )
        }
        node = InputFormDeriver(concepts=concepts).derive_concept(name="plain", concept_ref="docs.Plain")
        assert "hints" not in node.model_dump()
        assert all("hints" not in field for field in node.model_dump()["fields"])
