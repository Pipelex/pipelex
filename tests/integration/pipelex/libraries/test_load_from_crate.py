import tempfile
from collections.abc import Callable
from pathlib import Path

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.hub import clear_current_library, get_library_manager, set_current_library
from pipelex.libraries.library_crate_factory import LibraryCrateFactory

SCORING_MTHDS = """\
domain = "scoring"
description = "Scoring domain"
system_prompt = "You are a scoring assistant."
main_pipe = "compute_score"

[concept]
ScoreResult = "A scoring result"

[pipe.compute_score]
type = "PipeLLM"
description = "Compute a score"
inputs = { data = "Text" }
output = "ScoreResult"
model = "$quick-reasoning"
prompt = "Compute score from $data"
"""

ANALYTICS_MTHDS = """\
domain = "analytics"
description = "Analytics domain"

[concept]
AnalyticsResult = "An analytics result"

[pipe.analyze]
type = "PipeLLM"
description = "Analyze data"
inputs = { data = "Text" }
output = "AnalyticsResult"
model = "$quick-reasoning"
prompt = "Analyze $data"
"""


class TestLoadFromCrate:
    """Integration: crate path produces identical library content to blueprint path."""

    def test_crate_equivalence(self, load_empty_library: Callable[[], str]):
        """load_from_crate produces the same concept_refs, pipe_refs, and domain codes
        as load_from_blueprints for the same input bundles.
        """
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            scoring_path = Path(tmp_dir) / "scoring.mthds"
            analytics_path = Path(tmp_dir) / "analytics.mthds"
            scoring_path.write_text(SCORING_MTHDS, encoding="utf-8")
            analytics_path.write_text(ANALYTICS_MTHDS, encoding="utf-8")

            # Parse blueprints
            blueprints = [
                PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=scoring_path),
                PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=analytics_path),
            ]

            # Path A: load_from_blueprints (existing path)
            lib_id_a = load_empty_library()
            library_manager.load_from_blueprints(library_id=lib_id_a, blueprints=blueprints)
            library_a = library_manager.get_library(library_id=lib_id_a)

            # Collect refs from library A
            concept_refs_a = set(library_a.concept_library.root.keys())
            pipe_refs_a = set(library_a.pipe_library.root.keys())
            domain_codes_a = set(library_a.domain_library.root.keys())

            # Tear down library A
            library_manager.teardown(library_id=lib_id_a)

            # Path B: build crate then load_from_crate
            crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)

            lib_id_b = load_empty_library()
            library_manager.load_from_crate(library_id=lib_id_b, crate=crate)
            library_b = library_manager.get_library(library_id=lib_id_b)

            # Collect refs from library B
            concept_refs_b = set(library_b.concept_library.root.keys())
            pipe_refs_b = set(library_b.pipe_library.root.keys())
            domain_codes_b = set(library_b.domain_library.root.keys())

            # Assert equivalence
            assert concept_refs_a == concept_refs_b, f"Concept refs differ: {concept_refs_a} vs {concept_refs_b}"
            assert pipe_refs_a == pipe_refs_b, f"Pipe refs differ: {pipe_refs_a} vs {pipe_refs_b}"
            assert domain_codes_a == domain_codes_b, f"Domain codes differ: {domain_codes_a} vs {domain_codes_b}"

    def test_crate_preserves_main_pipe(self):
        """LibraryCrate preserves main_pipe from bundle domain metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            scoring_path = Path(tmp_dir) / "scoring.mthds"
            scoring_path.write_text(SCORING_MTHDS, encoding="utf-8")

            blueprints = [
                PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=scoring_path),
            ]

            crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
            assert "scoring" in crate.domains
            assert crate.domains["scoring"].main_pipe == "compute_score"

    def test_pipe_source_is_scoped_to_current_library(self, tmp_path: Path) -> None:
        """Same pipe refs loaded concurrently must retain each library's own source path."""
        first_path = tmp_path / "first.mthds"
        second_path = tmp_path / "second.mthds"
        first_path.write_text(SCORING_MTHDS, encoding="utf-8")
        second_path.write_text(SCORING_MTHDS, encoding="utf-8")
        first_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=first_path)
        second_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=second_path)
        library_manager = get_library_manager()
        first_library_id, _ = library_manager.open_library()
        second_library_id, _ = library_manager.open_library()

        try:
            library_manager.load_from_blueprints(library_id=first_library_id, blueprints=[first_blueprint])
            library_manager.load_from_blueprints(library_id=second_library_id, blueprints=[second_blueprint])

            set_current_library(library_id=first_library_id)
            assert library_manager.get_pipe_source("scoring.compute_score") == str(first_path)
            set_current_library(library_id=second_library_id)
            assert library_manager.get_pipe_source("scoring.compute_score") == str(second_path)
        finally:
            clear_current_library()
            library_manager.teardown(library_id=first_library_id)
            library_manager.teardown(library_id=second_library_id)
