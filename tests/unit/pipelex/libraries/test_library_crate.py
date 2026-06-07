import pytest

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from tests.unit.pipelex.libraries.test_library_crate_data import BlueprintSamples


class TestLibraryCrate:
    """Tests for LibraryCrate model and LibraryCrateFactory."""

    def test_json_round_trip(self):
        """LibraryCrate serializes to JSON and deserializes back identically."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
        )
        json_str = crate.model_dump_json()
        restored = LibraryCrate.model_validate_json(json_str)
        assert restored.concepts == crate.concepts
        assert restored.pipes == crate.pipes
        assert restored.domains == crate.domains
        assert restored.source_map == crate.source_map
        assert restored.fingerprint == crate.fingerprint

    def test_merge_same_domain(self):
        """Two bundles for the same domain merge their concepts and pipes."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE, BlueprintSamples.SCORING_EXTRA_BUNDLE],
        )
        assert "scoring.WeightedScore" in crate.concepts
        assert "scoring.ScoreBreakdown" in crate.concepts
        assert "scoring.compute_score" in crate.pipes
        assert "scoring.explain_score" in crate.pipes
        # Domain metadata: first-write-wins
        assert "scoring" in crate.domains
        assert crate.domains["scoring"].description == "Scoring domain"

    def test_merge_across_domains(self):
        """Bundles with different domains produce refs qualified with respective domains."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE, BlueprintSamples.ANALYTICS_BUNDLE],
        )
        assert "scoring.WeightedScore" in crate.concepts
        assert "analytics.Metric" in crate.concepts
        assert "scoring.compute_score" in crate.pipes
        assert "analytics.compute_metric" in crate.pipes
        assert "scoring" in crate.domains
        assert "analytics" in crate.domains

    def test_string_concept_preserved(self):
        """String-described concepts are preserved as strings (not converted to ConceptBlueprint)."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.STRING_CONCEPT_BUNDLE],
        )
        concept = crate.concepts["simple.MyConcept"]
        assert isinstance(concept, str)
        assert concept == "A simple concept described as a string"

    def test_concept_collision_cross_file_raises(self):
        """Two bundles from different files declaring the same concept_ref raise ConceptLibraryError."""
        with pytest.raises(ConceptLibraryError, match=r"two different bundle files"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SCORING_BUNDLE, BlueprintSamples.SCORING_DUPLICATE_CONCEPT_BUNDLE],
            )

    def test_concept_collision_same_file_raises(self):
        """Two bundles from the same file declaring the same concept_ref raise ConceptLibraryError."""
        with pytest.raises(ConceptLibraryError, match=r"declared twice in the same bundle file"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SCORING_BUNDLE, BlueprintSamples.SCORING_SAME_FILE_DUPLICATE_CONCEPT_BUNDLE],
            )

    def test_pipe_collision_cross_file_raises(self):
        """Two bundles from different files declaring the same pipe_ref raise PipeLibraryError."""
        with pytest.raises(PipeLibraryError, match=r"two different bundle files"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SCORING_BUNDLE, BlueprintSamples.SCORING_DUPLICATE_PIPE_BUNDLE],
            )

    def test_pipe_collision_same_file_raises(self):
        """Two bundles from the same file declaring the same pipe_ref raise PipeLibraryError."""
        with pytest.raises(PipeLibraryError, match=r"declared twice in the same bundle file"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SCORING_BUNDLE, BlueprintSamples.SCORING_SAME_FILE_DUPLICATE_PIPE_BUNDLE],
            )

    def test_fingerprint_determinism(self):
        """Same blueprints produce the same fingerprint; different blueprints produce different ones."""
        crate_a = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
        )
        crate_b = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
        )
        assert crate_a.fingerprint == crate_b.fingerprint
        assert crate_a.fingerprint != ""

        crate_c = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.ANALYTICS_BUNDLE],
        )
        assert crate_a.fingerprint != crate_c.fingerprint

    def test_empty_blueprints(self):
        """Bundle with no concepts and no pipes produces empty dicts and a valid fingerprint."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.EMPTY_BUNDLE],
        )
        assert crate.concepts == {}
        assert crate.pipes == {}
        assert "empty_domain" in crate.domains
        assert crate.fingerprint != ""

    def test_source_map_populated(self):
        """Source map tracks concept_ref and pipe_ref to their source file paths."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
        )
        assert crate.source_map["scoring.WeightedScore"] == "/fake/scoring.mthds"
        assert crate.source_map["scoring.compute_score"] == "/fake/scoring.mthds"

    def test_none_source_excluded_from_source_map(self):
        """Bundles with source=None produce valid crates but no source_map entries."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.NONE_SOURCE_BUNDLE],
        )
        assert "nosource.Item" in crate.concepts
        assert "nosource.process_item" in crate.pipes
        assert "nosource.Item" not in crate.source_map
        assert "nosource.process_item" not in crate.source_map

    def test_concept_collision_none_source_raises(self):
        """Two bundles with source=None declaring the same concept_ref raise ConceptLibraryError."""
        with pytest.raises(ConceptLibraryError, match=r"two different bundle files"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.NONE_SOURCE_BUNDLE, BlueprintSamples.NONE_SOURCE_DUPLICATE_CONCEPT_BUNDLE],
            )

    def test_signature_then_concrete_concrete_wins(self):
        """A signature followed by a concrete pipe reconciles: the concrete wins."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SIG_SIGNATURE_BUNDLE, BlueprintSamples.SIG_CONCRETE_BUNDLE],
        )
        winner = crate.pipes["reconcile.summarize"]
        assert winner.is_signature is False
        assert crate.source_map["reconcile.summarize"] == "/fake/reconcile_concrete.mthds"

    def test_concrete_then_signature_concrete_wins(self):
        """A concrete pipe followed by a signature reconciles the same way (order-independent)."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SIG_CONCRETE_BUNDLE, BlueprintSamples.SIG_SIGNATURE_BUNDLE],
        )
        winner = crate.pipes["reconcile.summarize"]
        assert winner.is_signature is False
        assert crate.source_map["reconcile.summarize"] == "/fake/reconcile_concrete.mthds"

    def test_signature_plus_signature_matching_is_order_independent(self):
        """Two matching signatures collapse to one, and the winner does not depend on load order."""
        crate_ab = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SIG_SIGNATURE_BUNDLE, BlueprintSamples.SIG_SIGNATURE_DUP_BUNDLE],
        )
        crate_ba = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SIG_SIGNATURE_DUP_BUNDLE, BlueprintSamples.SIG_SIGNATURE_BUNDLE],
        )
        assert crate_ab.pipes["reconcile.summarize"].is_signature is True
        assert crate_ba.pipes["reconcile.summarize"].is_signature is True
        # Deterministic tie-break: same surviving source and same fingerprint regardless of order.
        assert crate_ab.source_map["reconcile.summarize"] == crate_ba.source_map["reconcile.summarize"]
        assert crate_ab.fingerprint == crate_ba.fingerprint

    def test_signature_plus_signature_mismatched_raises(self):
        """Two signatures with differing contracts raise a PipeLibraryError."""
        with pytest.raises(PipeLibraryError, match=r"mismatched contracts"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SIG_SIGNATURE_BUNDLE, BlueprintSamples.SIG_SIGNATURE_MISMATCH_BUNDLE],
            )

    def test_signature_plus_concrete_mismatched_inputs_raises(self):
        """A signature and a concrete with differing inputs raise a PipeLibraryError."""
        with pytest.raises(PipeLibraryError, match=r"mismatched contracts"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SIG_SIGNATURE_BUNDLE, BlueprintSamples.SIG_CONCRETE_MISMATCH_BUNDLE],
            )

    def test_signature_with_inputs_plus_concrete_without_inputs_raises(self):
        """Exact-match: a header with explicit inputs and a concrete that omits them mismatch."""
        with pytest.raises(PipeLibraryError, match=r"mismatched contracts"):
            LibraryCrateFactory.make_from_blueprints(
                blueprints=[BlueprintSamples.SIG_SIGNATURE_BUNDLE, BlueprintSamples.SIG_CONCRETE_NO_INPUTS_BUNDLE],
            )

    @pytest.mark.parametrize(
        "blueprints",
        [
            [BlueprintSamples.SIG_SIGNATURE_BUNDLE, BlueprintSamples.SIG_CONCRETE_NO_SOURCE_BUNDLE],
            [BlueprintSamples.SIG_CONCRETE_NO_SOURCE_BUNDLE, BlueprintSamples.SIG_SIGNATURE_BUNDLE],
        ],
    )
    def test_sourceless_concrete_winner_clears_stale_source(self, blueprints: list[PipelexBundleBlueprint]):
        """A concrete with no source wins over a signature without leaving the signature's file in source_map."""
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
        assert crate.pipes["reconcile.summarize"].is_signature is False
        # The losing signature's file must not be misattributed to the winning concrete.
        assert "reconcile.summarize" not in crate.source_map

    @pytest.mark.parametrize(
        "blueprints",
        [
            # Header outputs bare `Summary`; concrete outputs same-domain-qualified `reconcile.Summary`.
            [BlueprintSamples.SIG_SIGNATURE_BARE_SUMMARY_BUNDLE, BlueprintSamples.SIG_CONCRETE_QUALIFIED_SUMMARY_BUNDLE],
            # Header contract uses `native.Text`; concrete uses bare native `Text`.
            [BlueprintSamples.SIG_SIGNATURE_NATIVE_QUALIFIED_BUNDLE, BlueprintSamples.SIG_CONCRETE_BUNDLE],
            # Same variable-length output, bare `Summary[]` vs qualified `reconcile.Summary[]`.
            [BlueprintSamples.SIG_SIGNATURE_LIST_BARE_BUNDLE, BlueprintSamples.SIG_CONCRETE_LIST_QUALIFIED_BUNDLE],
            # Same fixed-count output, bare `Summary[2]` vs qualified `reconcile.Summary[2]`.
            [BlueprintSamples.SIG_SIGNATURE_LIST_FIXED_BUNDLE, BlueprintSamples.SIG_CONCRETE_LIST_FIXED_QUALIFIED_BUNDLE],
            # Same external-domain output `other_domain.Insight` on both sides (kept verbatim).
            [BlueprintSamples.SIG_SIGNATURE_EXTERNAL_OUTPUT_BUNDLE, BlueprintSamples.SIG_CONCRETE_EXTERNAL_OUTPUT_BUNDLE],
        ],
    )
    def test_contracts_reconcile_across_equivalent_concept_spellings(self, blueprints: list[PipelexBundleBlueprint]):
        """Bare<->qualified, native, fixed-count, and external-domain spellings of the same contract reconcile (concrete wins)."""
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
        assert crate.pipes["reconcile.summarize"].is_signature is False

    @pytest.mark.parametrize(
        "blueprints",
        [
            # Differing multiplicity: `Summary[]` (header, variable) vs `reconcile.Summary` (concrete, single).
            [BlueprintSamples.SIG_SIGNATURE_LIST_BARE_BUNDLE, BlueprintSamples.SIG_CONCRETE_QUALIFIED_SUMMARY_BUNDLE],
            # Variable `Summary[]` vs fixed `reconcile.Summary[2]` — `[]` must NOT conflate with `[N]`.
            [BlueprintSamples.SIG_SIGNATURE_LIST_BARE_BUNDLE, BlueprintSamples.SIG_CONCRETE_LIST_FIXED_QUALIFIED_BUNDLE],
            # Regression guard: variable `Summary[]` vs fixed `reconcile.Summary[1]` — the exact pair the
            # `True == 1` bool/int conflation would have wrongly accepted.
            [BlueprintSamples.SIG_SIGNATURE_LIST_BARE_BUNDLE, BlueprintSamples.SIG_CONCRETE_LIST_ONE_QUALIFIED_BUNDLE],
            # Genuinely different output concept: `Brief` (header) vs `reconcile.Summary` (concrete).
            [BlueprintSamples.SIG_SIGNATURE_BRIEF_BUNDLE, BlueprintSamples.SIG_CONCRETE_QUALIFIED_SUMMARY_BUNDLE],
            # External-domain `other_domain.Insight` (header) vs same-domain bare `Summary` (concrete) — must not match.
            [BlueprintSamples.SIG_SIGNATURE_EXTERNAL_OUTPUT_BUNDLE, BlueprintSamples.SIG_CONCRETE_QUALIFIED_SUMMARY_BUNDLE],
        ],
    )
    def test_contracts_still_mismatch_when_genuinely_different(self, blueprints: list[PipelexBundleBlueprint]):
        """Differing multiplicity (incl. `[]` vs `[N]`), a different concept, or an external-domain ref still raises."""
        with pytest.raises(PipeLibraryError, match=r"mismatched contracts"):
            LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
