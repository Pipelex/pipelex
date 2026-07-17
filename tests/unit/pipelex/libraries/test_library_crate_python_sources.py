from typing import ClassVar

from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from tests.unit.pipelex.libraries.test_library_crate_data import BlueprintSamples


class TestLibraryCratePythonSources:
    """Sandbox-hosted source capture on the crate: round-trips, but never touches the fingerprint."""

    _SOURCES: ClassVar[dict[str, str]] = {
        "funcs/score.py": "from pipelex.core.memory.working_memory import WorkingMemory\n\n\ndef compute_score(working_memory): ...\n",
        "structures/weighted_score.py": "from pydantic import BaseModel\n\n\nclass WeightedScore(BaseModel):\n    value: float\n",
    }

    def test_python_sources_default_empty(self):
        """A crate built without python_sources carries an empty dict (local/direct mode)."""
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.SCORING_BUNDLE])
        assert crate.python_sources == {}

    def test_python_sources_round_trip(self):
        """python_sources survives a JSON round-trip verbatim, alongside the rest of the crate."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
            python_sources=self._SOURCES,
        )
        assert crate.python_sources == self._SOURCES

        restored = LibraryCrate.model_validate_json(crate.model_dump_json())
        assert restored.python_sources == self._SOURCES
        # The rest of the crate is unaffected by carrying source.
        assert restored.concepts == crate.concepts
        assert restored.pipes == crate.pipes
        assert restored.fingerprint == crate.fingerprint

    def test_fingerprint_excludes_python_sources(self):
        """The structural fingerprint is identical whether or not source travels, and regardless of its content.

        Folding source into the fingerprint would break load_from_crate's structural-dedupe contract,
        so two crates that differ ONLY in python_sources must hash the same.
        """
        bare = LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.SCORING_BUNDLE])
        with_sources = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
            python_sources=self._SOURCES,
        )
        other_sources = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
            python_sources={"funcs/score.py": "def compute_score(working_memory): return 42\n"},
        )

        assert bare.fingerprint != ""
        assert bare.fingerprint == with_sources.fingerprint
        assert with_sources.fingerprint == other_sources.fingerprint
        # And the instance method agrees: source is not part of compute_fingerprint.
        assert with_sources.compute_fingerprint() == bare.compute_fingerprint()
