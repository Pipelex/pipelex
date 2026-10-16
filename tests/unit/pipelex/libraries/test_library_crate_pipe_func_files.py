from typing import ClassVar

from pipelex.core.method_trees.tree_files import Base64FileEntry, TreeFileEntry
from pipelex.libraries.library_crate import SUBMITTED_PYTHON_ROOT_KEY, LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from tests.unit.pipelex.libraries.test_library_crate_data import BlueprintSamples


class TestLibraryCratePipeFuncFiles:
    """The files a PipeFunc call receives, captured on the crate: they round-trip, but never touch the fingerprint."""

    _FILES: ClassVar[dict[str, dict[str, TreeFileEntry]]] = {
        SUBMITTED_PYTHON_ROOT_KEY: {
            "funcs/score.py": "from pipelex.core.memory.working_memory import WorkingMemory\n\n\ndef compute_score(working_memory): ...\n",
            "structures/weighted_score.py": "from pydantic import BaseModel\n\n\nclass WeightedScore(BaseModel):\n    value: float\n",
            "data/logo.png": Base64FileEntry(base64="iVBORw0KGgo="),
        },
    }

    def test_pipe_func_files_default_empty(self):
        """A crate built without files carries an empty mapping (local/direct mode)."""
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.SCORING_BUNDLE])
        assert crate.pipe_func_files == {}

    def test_pipe_func_files_round_trip(self):
        """The files survive a JSON round-trip verbatim, a binary file as its base64, alongside the rest of the crate."""
        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
            pipe_func_files=self._FILES,
        )
        assert crate.pipe_func_files == self._FILES

        restored = LibraryCrate.model_validate_json(crate.model_dump_json())
        assert restored.pipe_func_files == self._FILES
        # The rest of the crate is unaffected by carrying files.
        assert restored.concepts == crate.concepts
        assert restored.pipes == crate.pipes
        assert restored.fingerprint == crate.fingerprint

    def test_fingerprint_excludes_pipe_func_files(self):
        """The structural fingerprint is identical whether or not files travel, and regardless of their content.

        Folding files into the fingerprint would break load_from_crate's structural-dedupe contract,
        so two crates that differ ONLY in pipe_func_files must hash the same.
        """
        bare = LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.SCORING_BUNDLE])
        with_files = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
            pipe_func_files=self._FILES,
        )
        other_files = LibraryCrateFactory.make_from_blueprints(
            blueprints=[BlueprintSamples.SCORING_BUNDLE],
            pipe_func_files={SUBMITTED_PYTHON_ROOT_KEY: {"funcs/score.py": "def compute_score(working_memory): return 42\n"}},
        )

        assert bare.fingerprint != ""
        assert bare.fingerprint == with_files.fingerprint
        assert with_files.fingerprint == other_files.fingerprint
        # And the instance method agrees: files are not part of compute_fingerprint.
        assert with_files.compute_fingerprint() == bare.compute_fingerprint()
