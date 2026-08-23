"""Effective intent hints assembled during refinement flattening (spec: library-crate.md step 3,
intent-hints.md Precedence and Inheritance): chain merge on both arms, position-correct memoization,
authored-only travel for field and slot hints, idempotency, and fingerprint sensitivity.
"""

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

MTHDS_TEST_VERSION = "0.0.0-test"


def _concept(ref: str, crate: LibraryCrate) -> ConceptBlueprint:
    value = crate.concepts[ref]
    assert isinstance(value, ConceptBlueprint)
    return value


def _hinted_chain_crate() -> LibraryCrate:
    """A refinement chain with hints at several positions, plus hinted field and slot sites."""
    return LibraryCrate(
        concepts={
            # Structured base with hints: the chain's bottom.
            "docs.Base": ConceptBlueprint(
                description="the structured base",
                structure={"body": ConceptStructureBlueprint(description="the body", type=ConceptStructureBlueprintFieldType.TEXT)},
                hints={"intent": "label", "emphasis": "base"},
            ),
            # Top DELIBERATELY declared before Mid: flattening iterates in declaration order, so
            # Top's resolution walks Mid -> Base in ONE pass and caches BOTH positions — the very
            # multi-position walk the memoization guard below needs to exist.
            # Top: no hints of its own — inherits Mid's effective hints.
            "docs.Top": ConceptBlueprint(description="the top link", refines="Mid"),
            # Mid-chain: overrides `intent`, keeps inheriting `emphasis`.
            "docs.Mid": ConceptBlueprint(description="the mid link", refines="Base", hints={"intent": "prose"}),
            # Sibling refining the BASE directly: must get the base's hints, not Mid's accumulated
            # ones, even when Mid's walk populated the cache first.
            "docs.Sibling": ConceptBlueprint(description="refines the base directly", refines="Base"),
            # Hint-free chain: the empty merge leaves no member.
            "docs.PlainBase": ConceptBlueprint(
                description="hint-free base",
                structure={"note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.TEXT)},
            ),
            "docs.PlainTop": ConceptBlueprint(description="hint-free refiner", refines="PlainBase"),
            # Native-backed arm: keeps `refines`, still assembles hints.
            "docs.Summary": ConceptBlueprint(description="a short summary", refines="Text", hints={"intent": "prose"}),
            "docs.LongSummary": ConceptBlueprint(description="a longer summary", refines="Summary"),
            # Field-site hints, carried as authored.
            "docs.Card": ConceptBlueprint(
                description="a card",
                structure={
                    "title": ConceptStructureBlueprint(
                        description="the title", type=ConceptStructureBlueprintFieldType.TEXT, hints={"intent": "label"}
                    )
                },
            ),
        },
        pipes={
            "docs.write": PipeLLMBlueprint(
                description="write a doc",
                inputs={"topic": InputSlotBlueprint(concept="Text", hints={"intent": "prose"}), "plain": "Text"},
                output="Text",
                prompt="Write about $topic using $plain",
            ),
        },
        domains={"docs": DomainBlueprint(code="docs", description="Docs domain")},
        source_map={},
    )


class TestEffectiveHintsAssembly:
    def test_flattened_arm_merges_chain_hints_nearer_wins(self):
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        mid = _concept("docs.Mid", result)
        assert mid.refines is None
        assert isinstance(mid.structure, dict)
        # Own `intent` wins over the base's; `emphasis` is inherited, not cleared.
        assert mid.hints == {"emphasis": "base", "intent": "prose"}

    def test_hintless_refiner_inherits_effective_hints(self):
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        top = _concept("docs.Top", result)
        assert top.hints == {"emphasis": "base", "intent": "prose"}

    def test_memoized_mid_chain_resolution_carries_its_own_positions_hints(self):
        # Top walks first (dict order), caching Mid AND Base positions in one pass. Sibling then
        # resolves Base FROM the cache — and must see Base's hints, not Mid's accumulated ones.
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        sibling = _concept("docs.Sibling", result)
        assert sibling.hints == {"emphasis": "base", "intent": "label"}

    def test_empty_merge_leaves_no_member(self):
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        assert _concept("docs.PlainTop", result).hints is None

    def test_native_backed_arm_keeps_refines_and_assembles_hints(self):
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        summary = _concept("docs.Summary", result)
        assert summary.refines == "native.Text"
        assert summary.hints == {"intent": "prose"}
        long_summary = _concept("docs.LongSummary", result)
        assert long_summary.refines == "docs.Summary"
        assert long_summary.hints == {"intent": "prose"}


class TestAuthoredHintsTravel:
    def test_field_hints_carried_as_authored(self):
        # No site-over-concept merge at crate level — that merge is the deriver's.
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        card = _concept("docs.Card", result)
        assert isinstance(card.structure, dict)
        title = card.structure["title"]
        assert isinstance(title, ConceptStructureBlueprint)
        assert title.hints == {"intent": "label"}

    def test_slot_hints_carried_as_authored_with_concept_qualified(self):
        result = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        pipe = result.pipes["docs.write"]
        assert pipe.inputs is not None
        slot = pipe.inputs["topic"]
        assert isinstance(slot, InputSlotBlueprint)
        assert slot.concept == "native.Text"
        assert slot.hints == {"intent": "prose"}
        assert pipe.inputs["plain"] == "native.Text"


class TestHintedCrateStability:
    def test_normalization_is_idempotent_on_hinted_crate(self):
        once = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)
        twice = normalize_crate(once, mthds_version=MTHDS_TEST_VERSION)
        assert twice.fingerprint == once.fingerprint
        assert twice.concepts == once.concepts
        assert twice.pipes == once.pipes

    def test_hinted_crate_fingerprint_differs_from_hint_free_twin(self):
        hinted = normalize_crate(_hinted_chain_crate(), mthds_version=MTHDS_TEST_VERSION)

        twin = _hinted_chain_crate()
        stripped_concepts = {
            ref: value.model_copy(update={"hints": None}) if isinstance(value, ConceptBlueprint) else value for ref, value in twin.concepts.items()
        }
        hint_free = LibraryCrate(
            concepts=stripped_concepts,
            pipes=twin.pipes,
            domains=twin.domains,
            source_map=twin.source_map,
        )
        hint_free_normalized = normalize_crate(hint_free, mthds_version=MTHDS_TEST_VERSION)
        assert hint_free_normalized.fingerprint != hinted.fingerprint
