import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
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

    def test_string_concept_normalization(self):
        """String-described concepts are normalized to ConceptBlueprint."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.STRING_CONCEPT_BUNDLE],
        )
        concept = crate.concepts["simple.MyConcept"]
        assert isinstance(concept, ConceptBlueprint)
        assert concept.description == "A simple concept described as a string"

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
