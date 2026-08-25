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
from pipelex.pipeline.hint_warnings import MAX_AUTHORED_TOKEN_LENGTH, MAX_HINT_FINDINGS_PER_SITE, build_hint_warnings
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

    def test_choice_field_is_not_a_text_site(self):
        """Choices dominate the declared type (the deriver emits an enum), so a text intent on a
        typed-choice field is inapplicable and must warn.
        """
        warnings = _lint(
            _crate(
                {
                    "docs.Card": ConceptBlueprint(
                        description="a card",
                        structure={
                            "mood": ConceptStructureBlueprint(
                                description="the mood",
                                type=ConceptStructureBlueprintFieldType.TEXT,
                                choices=["calm", "wild"],
                                hints={"intent": "prose"},
                            )
                        },
                    )
                }
            )
        )
        assert len(warnings) == 1
        assert warnings[0].error_type == HintLintErrorType.HINT_INAPPLICABLE_INTENT

    def test_class_backed_native_text_concept_takes_text_intents(self):
        """A `structure = "TextContent"` concept IS the native Text payload: the deriver honors a
        `prose`/`label` hint there, so the lint must not call it inapplicable.
        """
        warnings = _lint(_crate({"docs.Styled": ConceptBlueprint(description="styled text", structure="TextContent", hints={"intent": "prose"})}))
        assert warnings == []

    def test_class_backed_native_number_concept_takes_number_intents(self):
        warnings = _lint(_crate({"docs.Score": ConceptBlueprint(description="a score", structure="NumberContent", hints={"intent": "rating"})}))
        assert warnings == []

    def test_class_backed_project_class_is_not_a_hint_site(self):
        # A registered non-native class is an object payload: intent words do not apply.
        warnings = _lint(_crate({"docs.Custom": ConceptBlueprint(description="custom", structure="SomeProjectClass", hints={"intent": "prose"})}))
        assert len(warnings) == 1
        assert warnings[0].error_type == HintLintErrorType.HINT_INAPPLICABLE_INTENT

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


class TestHintLintPayloadBounds:
    """Authored hint content is interpolated raw into `message`, and one finding fires per unknown
    key — so a site that names many keys, or one very long value, could inflate the warning payload
    of a channel an author invokes casually. Both are bounded.
    """

    def test_undefined_keys_beyond_the_cap_collapse_into_one_tail(self):
        hints = {f"key_{index:02d}": "value" for index in range(MAX_HINT_FINDINGS_PER_SITE + 4)}
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints=hints)}))

        assert len(warnings) == MAX_HINT_FINDINGS_PER_SITE + 1
        assert all(warning.error_type == HintLintErrorType.HINT_UNKNOWN_KEY for warning in warnings)
        assert warnings[-1].message.startswith("...and 4 more hint key(s) on concept 'docs.Essay'")

    def test_exactly_the_cap_reports_every_key_with_no_tail(self):
        hints = {f"key_{index:02d}": "value" for index in range(MAX_HINT_FINDINGS_PER_SITE)}
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints=hints)}))

        assert len(warnings) == MAX_HINT_FINDINGS_PER_SITE
        assert not any("more hint key(s)" in warning.message for warning in warnings)

    def test_the_cap_is_per_site_not_per_crate(self):
        hints = {f"key_{index:02d}": "value" for index in range(MAX_HINT_FINDINGS_PER_SITE)}
        warnings = _lint(
            _crate(
                {
                    "docs.Essay": ConceptBlueprint(description="an essay", hints=hints),
                    "docs.Memo": ConceptBlueprint(description="a memo", hints=hints),
                }
            )
        )
        assert len(warnings) == 2 * MAX_HINT_FINDINGS_PER_SITE

    def test_a_long_authored_key_is_elided_in_the_message(self):
        long_key = "k" * (MAX_AUTHORED_TOKEN_LENGTH + 50)
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints={long_key: "value"})}))

        assert len(warnings) == 1
        assert long_key not in warnings[0].message
        assert f"'{'k' * MAX_AUTHORED_TOKEN_LENGTH}...'" in warnings[0].message

    def test_a_long_authored_intent_value_is_elided_in_the_message(self):
        long_word = "w" * (MAX_AUTHORED_TOKEN_LENGTH + 50)
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints={"intent": long_word})}))

        assert len(warnings) == 1
        assert warnings[0].error_type == HintLintErrorType.HINT_UNKNOWN_INTENT
        assert long_word not in warnings[0].message
        assert f"'{'w' * MAX_AUTHORED_TOKEN_LENGTH}...'" in warnings[0].message

    def test_a_token_at_the_length_limit_is_quoted_whole(self):
        exact_key = "k" * MAX_AUTHORED_TOKEN_LENGTH
        warnings = _lint(_crate({"docs.Essay": ConceptBlueprint(description="an essay", hints={exact_key: "value"})}))

        assert f"'{exact_key}'" in warnings[0].message
        assert "..." not in warnings[0].message
