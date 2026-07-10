import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.exceptions import CrateNormalizationError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

MTHDS_TEST_VERSION = "0.1.0-test"


def _structure_field(concept: ConceptBlueprint | str, field_name: str) -> ConceptStructureBlueprint:
    """Narrow a concept's structure field to a `ConceptStructureBlueprint` for typed assertions."""
    assert isinstance(concept, ConceptBlueprint)
    assert isinstance(concept.structure, dict)
    field = concept.structure[field_name]
    assert isinstance(field, ConceptStructureBlueprint)
    return field


def _authored_crate() -> LibraryCrate:
    """A merged, key-qualified single-package crate exercising every normalization step.

    All keys are domain-qualified (`scoring.*`) as `LibraryCrateFactory` would leave them; in-body
    references are authored bare (same-domain codes and native codes) so the normalizer has work to do.
    """
    return LibraryCrate(
        concepts={
            # String-described concept -> promoted to a description-only ConceptBlueprint.
            "scoring.Category": "A category label",
            # Structure with a bare same-domain concept_ref and a bare native concept_ref.
            "scoring.WeightedScore": ConceptBlueprint(
                description="A weighted score",
                structure={
                    "value": ConceptStructureBlueprint(description="the numeric value", type=ConceptStructureBlueprintFieldType.NUMBER),
                    "label": ConceptStructureBlueprint(
                        description="the category", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Category"
                    ),
                    "note": ConceptStructureBlueprint(
                        description="a free-text note", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Text"
                    ),
                },
            ),
            # Refines a same-package concept that HAS a structure -> flattened (refines dropped).
            "scoring.DetailedScore": ConceptBlueprint(description="a detailed score", refines="WeightedScore"),
            # Refines a STRUCTURELESS native (Image) -> refines kept, no structure materialized.
            "scoring.CustomImage": ConceptBlueprint(description="a domain-specific image", refines="Image"),
            # Refines a STRUCTURED native (Text, whose materialized structure has a `text` field) ->
            # refines kept (B1-2): flattening would drop the native base on round-trip.
            "scoring.Summary": ConceptBlueprint(description="a short summary", refines="Text"),
            # Multi-hop: refines a concept that itself bottoms out at a native -> refines kept.
            "scoring.LongSummary": ConceptBlueprint(description="a longer summary", refines="Summary"),
        },
        pipes={
            "scoring.compute_score": PipeLLMBlueprint(
                description="Compute a weighted score",
                inputs={"data": "Text"},
                output="WeightedScore",
                prompt="Compute from $data",
            ),
            "scoring.list_scores": PipeLLMBlueprint(
                description="Compute several weighted scores",
                inputs={"docs": "Text[]"},
                output="WeightedScore[]",
                prompt="List from $docs",
            ),
            "scoring.pipeline": PipeSequenceBlueprint(
                description="Run the scoring pipeline",
                output="WeightedScore",
                steps=[SubPipeBlueprint(pipe="compute_score")],
            ),
        },
        domains={"scoring": DomainBlueprint(code="scoring", description="Scoring domain")},
        source_map={"scoring.WeightedScore": "/fake/scoring.mthds"},
    )


class TestCrateNormalization:
    """Unit tests for `normalize_crate` over a hand-built, key-qualified crate."""

    def test_string_concept_promoted_to_blueprint(self):
        """A string-described concept becomes an explicit description-only ConceptBlueprint."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        category = result.concepts["scoring.Category"]
        assert isinstance(category, ConceptBlueprint)
        assert category.description == "A category label"
        assert category.structure is None

    def test_in_body_concept_refs_fully_qualified(self):
        """Bare same-domain and bare native concept refs in a structure become fully qualified."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        weighted = result.concepts["scoring.WeightedScore"]
        assert _structure_field(weighted, "label").concept_ref == "scoring.Category"
        assert _structure_field(weighted, "note").concept_ref == "native.Text"

    def test_pipe_io_refs_qualified_with_multiplicity_preserved(self):
        """Pipe input/output concept refs qualify; multiplicity markers survive the rewrite."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        compute = result.pipes["scoring.compute_score"]
        assert compute.inputs == {"data": "native.Text"}
        assert compute.output == "scoring.WeightedScore"
        listed = result.pipes["scoring.list_scores"]
        assert listed.inputs == {"docs": "native.Text[]"}
        assert listed.output == "scoring.WeightedScore[]"

    def test_sequence_step_pipe_refs_qualified(self):
        """A sequence step's bare pipe ref is qualified with the pipe's owner domain."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        pipeline = result.pipes["scoring.pipeline"]
        assert isinstance(pipeline, PipeSequenceBlueprint)
        assert pipeline.steps[0].pipe == "scoring.compute_score"

    def test_refinement_with_structured_base_is_flattened(self):
        """Refining a concept with a structure adopts that (qualified) structure and drops `refines`."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        detailed = result.concepts["scoring.DetailedScore"]
        assert isinstance(detailed, ConceptBlueprint)
        assert detailed.refines is None
        assert isinstance(detailed.structure, dict)
        assert set(detailed.structure.keys()) == {"value", "label", "note"}
        # The adopted structure carries the base's already-qualified refs.
        assert _structure_field(detailed, "label").concept_ref == "scoring.Category"
        assert _structure_field(detailed, "note").concept_ref == "native.Text"

    def test_refinement_with_structureless_native_base_keeps_refines(self):
        """Refining a structureless native (Image) keeps a qualified `refines` and stays structureless."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        custom_image = result.concepts["scoring.CustomImage"]
        assert isinstance(custom_image, ConceptBlueprint)
        assert custom_image.refines == "native.Image"
        assert custom_image.structure is None

    def test_refinement_with_structured_native_base_keeps_refines(self):
        """Refining a STRUCTURED native (Text) keeps the qualified `refines` and is NOT flattened (B1-2).

        The old behavior inlined native.Text's `text` field and dropped `refines`, which loses the
        native content class on round-trip. The native is materialized separately (step 4), so keeping
        the link is both sufficient and identity-preserving.
        """
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        summary = result.concepts["scoring.Summary"]
        assert isinstance(summary, ConceptBlueprint)
        assert summary.refines == "native.Text"
        assert summary.structure is None
        # The native base it points at is materialized in the crate (so the link resolves).
        assert "native.Text" in result.concepts

    def test_multi_hop_native_backed_chain_keeps_refines(self):
        """A concept whose refinement chain reaches a native only through an intermediate keeps `refines`."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        long_summary = result.concepts["scoring.LongSummary"]
        assert isinstance(long_summary, ConceptBlueprint)
        # Not flattened: the chain LongSummary -> Summary -> native.Text bottoms at a native.
        assert long_summary.refines == "scoring.Summary"
        assert long_summary.structure is None

    def test_referenced_natives_are_materialized(self):
        """Every referenced native is materialized as a `native.<Code>` concept entry."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        # native.Text is referenced by a structure field (and pipe io); it materializes WITH a structure.
        text_native = result.concepts["native.Text"]
        assert isinstance(text_native, ConceptBlueprint)
        assert isinstance(text_native.structure, dict)
        assert "text" in text_native.structure
        # native.Image is referenced via a `refines`; it is a structureless native.
        image_native = result.concepts["native.Image"]
        assert isinstance(image_native, ConceptBlueprint)
        assert image_native.structure is None

    def test_unreferenced_natives_absent(self):
        """Natives that nothing references are not materialized into the crate."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        assert "native.SearchResult" not in result.concepts
        assert "native.Page" not in result.concepts

    def test_fingerprint_recomputed_and_version_stamped(self):
        """The normalized crate carries the D2-scope fingerprint and the mthds_version stamp."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        assert result.mthds_version == MTHDS_TEST_VERSION
        assert result.fingerprint != ""
        assert result.fingerprint == result.compute_normalized()

    def test_normalization_is_idempotent(self):
        """Normalizing an already-normalized crate is a fixed point (content and fingerprint)."""
        once = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        twice = normalize_crate(once, mthds_version=MTHDS_TEST_VERSION)
        assert twice.fingerprint == once.fingerprint
        assert twice.concepts == once.concepts
        assert twice.pipes == once.pipes
        assert twice.domains == once.domains

    def test_non_domain_qualified_key_raises(self):
        """A crate key that is not domain-qualified is a contract violation, surfaced explicitly."""
        crate = LibraryCrate(concepts={"BareConcept": "a concept with no domain in its key"})
        with pytest.raises(CrateNormalizationError, match="not domain-qualified"):
            normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)
