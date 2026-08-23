import tempfile
from collections.abc import Callable
from pathlib import Path

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint

MTHDS_TEST_VERSION = "0.0.0-test"

REPORT_MTHDS = """\
domain = "report"
description = "Report domain"

[concept.Score]
description = "A weighted score"
structure = { value = "the numeric value", note = { description = "a free-text note", type = "concept", concept_ref = "Text" } }

[concept.Snapshot]
description = "A domain-specific image"
refines = "Image"

[pipe.make_score]
type = "PipeLLM"
description = "Compute a score"
inputs = { data = "Text" }
output = "Score"
model = "$quick-reasoning"
prompt = "Compute a score from $data"
"""

INTAKE_MTHDS = """\
domain = "intake"
description = "Document intake domain"

[pipe.extract_pages]
type = "PipeExtract"
description = "Extract the pages of a document"
inputs = { doc = "Document" }
output = "Page[]"
"""


class TestCrateNormalizationRoundTrip:
    """Integration: a normalized crate (natives materialized) loads back into a live library."""

    def test_normalized_crate_loads_and_validates(self, load_empty_library: Callable[[], str]):
        """normalize_crate materializes `native.*` entries; load_from_crate must skip them and still
        load the authored concepts/pipes, then pass validate_library — proving the round-trip (D6).
        """
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "report.mthds"
            report_path.write_text(REPORT_MTHDS, encoding="utf-8")
            blueprints = [MthdsParser.make_pipelex_bundle_blueprint(bundle_path=report_path)]

            crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
            normalized = normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)

            # The normalized crate must carry materialized native entries (the very thing the loader
            # has to tolerate): `native.Text` (referenced by a field + pipe io) and `native.Image`
            # (referenced by a `refines`).
            assert "native.Text" in normalized.concepts
            assert "native.Image" in normalized.concepts

            library_id = load_empty_library()
            # Would raise ConceptLibraryError("Concept 'native.Text' already exists") without the skip.
            library_manager.load_from_crate(library_id=library_id, crate=normalized)
            library = library_manager.get_library(library_id=library_id)

            # Authored content is present with fully-qualified refs.
            assert "report.Score" in library.concept_library.root
            assert "report.Snapshot" in library.concept_library.root
            assert "report.make_score" in library.pipe_library.root
            # Natives remain singly-registered (pre-registered natives, not the crate's copies).
            assert "native.Text" in library.concept_library.root

    def test_extract_pipe_survives_normalization(self, load_empty_library: Callable[[], str]):
        """A PipeExtract declares `output = "Page[]"`, which normalization qualifies to
        `native.Page[]` before rebuilding the blueprints — which re-runs PipeExtractBlueprint's own
        output validator on the normalized spelling. A validator that only accepted the authoring
        spelling rejected its own normalized output, raising a raw pydantic ValidationError out of
        normalize_crate and 500-ing every static-core API route.
        """
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            intake_path = Path(tmp_dir) / "intake.mthds"
            intake_path.write_text(INTAKE_MTHDS, encoding="utf-8")
            blueprints = [MthdsParser.make_pipelex_bundle_blueprint(bundle_path=intake_path)]

            crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
            normalized = normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)

            assert normalized.pipes["intake.extract_pages"].output == "native.Page[]"

            # Normalization is idempotent: re-normalizing re-validates the already-normalized
            # blueprints, which is exactly the round trip the authoring-only validator broke.
            renormalized = normalize_crate(normalized, mthds_version=MTHDS_TEST_VERSION)
            assert renormalized.pipes["intake.extract_pages"].output == "native.Page[]"
            assert renormalized.fingerprint == normalized.fingerprint

            library_id = load_empty_library()
            library_manager.load_from_crate(library_id=library_id, crate=normalized)
            library = library_manager.get_library(library_id=library_id)
            assert "intake.extract_pages" in library.pipe_library.root

    def test_hinted_crate_round_trips_and_loads(self, load_empty_library: Callable[[], str]):
        """The committed hinted fixture (hints at all three sites) normalizes, re-normalizes to a
        fixed point, and loads back into a live library — hints riding the crate, never the runtime.
        """
        library_manager = get_library_manager()

        hinted_path = Path(__file__).parents[3] / "data" / "input_semantics" / "hinted_bundle.mthds"
        blueprints = [MthdsParser.make_pipelex_bundle_blueprint(bundle_path=hinted_path)]
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
        normalized = normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)

        # Hints are in the normalized crate: effective on concepts, as authored on slots.
        special_badge = normalized.concepts["input_semantics_hinted.SpecialBadge"]
        assert isinstance(special_badge, ConceptBlueprint)
        assert special_badge.hints == {"intent": "prose"}
        plain_badge = normalized.concepts["input_semantics_hinted.PlainBadge"]
        assert isinstance(plain_badge, ConceptBlueprint)
        assert plain_badge.hints == {"intent": "label"}
        hinted_pipe_inputs = normalized.pipes["input_semantics_hinted.hinted_slots"].inputs
        assert hinted_pipe_inputs is not None
        hinted_slot = hinted_pipe_inputs["hinted"]
        assert isinstance(hinted_slot, InputSlotBlueprint)
        assert hinted_slot.hints == {"intent": "prose"}

        renormalized = normalize_crate(normalized, mthds_version=MTHDS_TEST_VERSION)
        assert renormalized.fingerprint == normalized.fingerprint
        assert renormalized.concepts == normalized.concepts
        assert renormalized.pipes == normalized.pipes

        library_id = load_empty_library()
        library_manager.load_from_crate(library_id=library_id, crate=normalized)
        library = library_manager.get_library(library_id=library_id)
        assert "input_semantics_hinted.hinted_slots" in library.pipe_library.root
        # Runtime stays hint-free: the loaded pipe's StuffSpec sees only the concept.
        loaded_pipe = library.pipe_library.root["input_semantics_hinted.hinted_slots"]
        assert "hinted" in loaded_pipe.inputs.root
