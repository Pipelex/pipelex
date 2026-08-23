"""The advisory intent-hints lint (spec: intent-hints.md SHOULD-warn rules): each finding fires
with site attribution, warns without rejecting, and leaves the warned content in the crate.
"""

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_qualification import qualify_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipeline.hint_warnings import build_hint_warnings
from pipelex.validation_error_types import HintLintErrorType


def _lint(crate: LibraryCrate):
    return build_hint_warnings(qualify_crate(crate))


def _crate(concepts: dict[str, ConceptBlueprint | str], pipes: dict[str, PipeBlueprintUnion] | None = None) -> LibraryCrate:
    return LibraryCrate(
        concepts=concepts,
        pipes=pipes or {},
        domains={"docs": DomainBlueprint(code="docs", description="Docs domain")},
        source_map={},
    )


class TestHintLintFindings:
    def test_unknown_hint_key_warns_with_concept_attribution(self):
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints={"emphasis": "strong"})}))
        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.error_type == HintLintErrorType.HINT_UNKNOWN_KEY
        assert warning.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert warning.concept_code == "Essay"
        assert warning.domain_code == "docs"
        assert "emphasis" in warning.message

    def test_unknown_intent_word_warns(self):
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints={"intent": "poetry"})}))
        assert len(warnings) == 1
        assert warnings[0].error_type == HintLintErrorType.HINT_UNKNOWN_INTENT
        assert "poetry" in warnings[0].message

    def test_inapplicable_intent_warns_on_structured_concept(self):
        # A structured concept is neither text- nor number-valued: `prose` does not apply there.
        warnings = _lint(
            _crate(
                {
                    "docs.Card": ConceptBlueprint(
                        description="a card",
                        structure={"title": ConceptStructureBlueprint(description="the title", type=ConceptStructureBlueprintFieldType.TEXT)},
                        hints={"intent": "prose"},
                    )
                }
            )
        )
        assert len(warnings) == 1
        assert warnings[0].error_type == HintLintErrorType.HINT_INAPPLICABLE_INTENT

    def test_inapplicable_intent_warns_on_number_field_with_text_word(self):
        warnings = _lint(
            _crate(
                {
                    "docs.Review": ConceptBlueprint(
                        description="a review",
                        structure={
                            "stars": ConceptStructureBlueprint(
                                description="the stars", type=ConceptStructureBlueprintFieldType.INTEGER, hints={"intent": "prose"}
                            )
                        },
                    )
                }
            )
        )
        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.error_type == HintLintErrorType.HINT_INAPPLICABLE_INTENT
        assert warning.concept_code == "Review"
        assert warning.field_name == "stars"

    def test_inapplicable_intent_warns_on_slot_with_attribution(self):
        warnings = _lint(
            _crate(
                {"docs.Amount": ConceptBlueprint(description="an amount", refines="Number")},
                {
                    "docs.write": PipeLLMBlueprint(
                        description="write",
                        inputs={"amount": InputSlotBlueprint(concept="Amount", hints={"intent": "label"})},
                        output="Text",
                        prompt="Use $amount",
                    )
                },
            )
        )
        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.error_type == HintLintErrorType.HINT_INAPPLICABLE_INTENT
        assert warning.pipe_code == "write"
        assert warning.variable_names == ["amount"]


class TestHintLintSilence:
    def test_applicable_hints_produce_no_warning(self):
        warnings = _lint(
            _crate(
                {
                    # Description-only concept: text-valued -> `prose` applies.
                    "docs.Essay": ConceptBlueprint(description="an essay", hints={"intent": "prose"}),
                    # Refinement chain to native.Number -> `rating` applies.
                    "docs.Score": ConceptBlueprint(description="a score", refines="Number", hints={"intent": "rating"}),
                    # Text field -> `label` applies.
                    "docs.Card": ConceptBlueprint(
                        description="a card",
                        structure={
                            "title": ConceptStructureBlueprint(
                                description="the title", type=ConceptStructureBlueprintFieldType.TEXT, hints={"intent": "label"}
                            ),
                            # List of text: plural site judged per item -> text-valued.
                            "tags": ConceptStructureBlueprint(
                                description="the tags",
                                type=ConceptStructureBlueprintFieldType.LIST,
                                item_type="text",
                                hints={"intent": "label"},
                            ),
                        },
                    ),
                },
                {
                    # Slot with multiplicity: judged per item against the concept.
                    "docs.write": PipeLLMBlueprint(
                        description="write",
                        inputs={"essays": InputSlotBlueprint(concept="Essay[]", hints={"intent": "prose"})},
                        output="Text",
                        prompt="Use $essays",
                    )
                },
            )
        )
        assert warnings == []

    def test_hint_free_crate_produces_no_warning(self):
        warnings = _lint(
            _crate(
                {
                    "docs.Plain": ConceptBlueprint(description="plain"),
                    "docs.Str": "a string-described concept",
                }
            )
        )
        assert warnings == []

    def test_warned_content_stays_in_the_crate(self):
        # The lint names the finding; the crate keeps the authored entry untouched.
        crate = _crate({"docs.Essay": ConceptBlueprint(description="an essay", hints={"emphasis": "strong"})})
        warnings = _lint(crate)
        assert len(warnings) == 1
        qualified = qualify_crate(crate)
        essay = qualified.concepts["docs.Essay"]
        assert isinstance(essay, ConceptBlueprint)
        assert essay.hints == {"emphasis": "strong"}


class TestHintLintOrdering:
    def test_findings_are_deterministically_ordered(self):
        crate = _crate(
            {
                "docs.Beta": ConceptBlueprint(description="b", hints={"zz": "1"}),
                "docs.Alpha": ConceptBlueprint(description="a", hints={"aa": "1"}),
            }
        )
        first = [(w.error_type, w.concept_code) for w in _lint(crate)]
        second = [(w.error_type, w.concept_code) for w in _lint(crate)]
        assert first == second
        assert [code for _, code in first] == ["Alpha", "Beta"]
