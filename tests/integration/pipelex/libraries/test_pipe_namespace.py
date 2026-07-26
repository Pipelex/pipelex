"""Integration tests for pipe namespace (pipe_ref) indexing with real .mthds files."""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError

SCORING_MTHDS = """\
domain = "scoring"
description = "Scoring domain"

[concept]
ScoreResult = "A scoring result"

[pipe.process]
type = "PipeLLM"
description = "Process scoring data"
inputs = { data = "Text" }
output = "ScoreResult"
model = "$quick-reasoning"
prompt = "Process scoring from $data"
"""

ANALYTICS_MTHDS = """\
domain = "analytics"
description = "Analytics domain"

[concept]
AnalyticsResult = "An analytics result"

[pipe.process]
type = "PipeLLM"
description = "Process analytics data"
inputs = { data = "Text" }
output = "AnalyticsResult"
model = "$quick-reasoning"
prompt = "Process analytics from $data"
"""

SCORING_CORE_MTHDS = """\
domain = "scoring"
description = "Scoring core"

[pipe.compute_score]
type = "PipeLLM"
description = "Compute a score"
inputs = { data = "Text" }
output = "Text"
model = "$quick-reasoning"
prompt = "Compute score from $data"
"""

SCORING_ADVANCED_MTHDS = """\
domain = "scoring"
description = "Scoring advanced"

[pipe.weighted_score]
type = "PipeLLM"
description = "Compute a weighted score"
inputs = { data = "Text" }
output = "Text"
model = "$quick-reasoning"
prompt = "Compute weighted score from $data"
"""

SCORING_DUPLICATE_MTHDS = """\
domain = "scoring"
description = "Scoring duplicate"

[pipe.compute_score]
type = "PipeLLM"
description = "Duplicate compute score"
inputs = { data = "Text" }
output = "Text"
model = "$quick-reasoning"
prompt = "Duplicate compute score from $data"
"""

SCORING_CONCEPT_A_MTHDS = """\
domain = "scoring"
description = "Scoring with concept A"

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

SCORING_CONCEPT_B_MTHDS = """\
domain = "scoring"
description = "Scoring with concept B"

[concept]
ScoreResult = "A scoring result (duplicate)"

[pipe.weighted_score]
type = "PipeLLM"
description = "Compute a weighted score"
inputs = { data = "Text" }
output = "ScoreResult"
model = "$quick-reasoning"
prompt = "Compute weighted score from $data"
"""

SINGLE_DOMAIN_MTHDS = """\
domain = "scoring"
description = "Scoring domain"

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


class TestPipeNamespace:
    """Integration tests for pipe_ref-based namespace indexing."""

    def test_same_pipe_code_different_domains(self, load_test_library: Callable[[list[Path]], None]):
        """Two domains with the same pipe code coexist — would have collided under old bare-code indexing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "scoring.mthds").write_text(SCORING_MTHDS, encoding="utf-8")
            (Path(tmp_dir) / "analytics.mthds").write_text(ANALYTICS_MTHDS, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library = get_library_manager().get_current_library()

            # Both pipes retrievable by domain-qualified pipe_ref
            scoring_pipe = library.pipe_library.get_required_pipe("scoring.process")
            analytics_pipe = library.pipe_library.get_required_pipe("analytics.process")

            assert scoring_pipe.code == "process"
            assert scoring_pipe.domain_code == "scoring"
            assert analytics_pipe.code == "process"
            assert analytics_pipe.domain_code == "analytics"

            # Bare code is ambiguous
            with pytest.raises(PipeLibraryError, match="Ambiguous pipe code"):
                library.pipe_library.get_optional_pipe("process")

    def test_multi_bundle_same_domain(self, load_test_library: Callable[[list[Path]], None]):
        """Multiple .mthds files contributing to the same domain load successfully."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "scoring_core.mthds").write_text(SCORING_CORE_MTHDS, encoding="utf-8")
            (Path(tmp_dir) / "scoring_advanced.mthds").write_text(SCORING_ADVANCED_MTHDS, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library = get_library_manager().get_current_library()

            # Both pipes from the same domain exist
            compute_pipe = library.pipe_library.get_required_pipe("scoring.compute_score")
            weighted_pipe = library.pipe_library.get_required_pipe("scoring.weighted_score")

            assert compute_pipe.domain_code == "scoring"
            assert weighted_pipe.domain_code == "scoring"

            # Domain exists once
            assert library.domain_library.get_domain("scoring") is not None

    def test_duplicate_pipe_same_domain_raises(self, load_empty_library: Callable[[], str]):
        """Two .mthds files with the same domain and same pipe code raises on load."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "scoring_core.mthds").write_text(SCORING_CORE_MTHDS, encoding="utf-8")
            (Path(tmp_dir) / "scoring_duplicate.mthds").write_text(SCORING_DUPLICATE_MTHDS, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(PipeLibraryError):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_duplicate_concept_same_domain_raises(self, load_empty_library: Callable[[], str]):
        """Two .mthds files with the same domain and same concept code raises on load."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "scoring_a.mthds").write_text(SCORING_CONCEPT_A_MTHDS, encoding="utf-8")
            (Path(tmp_dir) / "scoring_b.mthds").write_text(SCORING_CONCEPT_B_MTHDS, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(ConceptLibraryError, match="declared in two different bundle files"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_bare_code_lookup_from_mthds(self, load_test_library: Callable[[list[Path]], None]):
        """Bare code lookup works when pipe code is unambiguous (single domain)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "scoring.mthds").write_text(SINGLE_DOMAIN_MTHDS, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library = get_library_manager().get_current_library()

            # Both bare code and pipe_ref lookup work
            pipe_by_ref = library.pipe_library.get_required_pipe("scoring.compute_score")
            pipe_by_code = library.pipe_library.get_required_pipe("compute_score")

            assert pipe_by_ref is pipe_by_code
            assert pipe_by_ref.pipe_ref == "scoring.compute_score"

    def test_wrong_domain_lookup_returns_not_found(self, load_test_library: Callable[[list[Path]], None]):
        """Looking up a pipe with the wrong domain raises PipeNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "scoring.mthds").write_text(SINGLE_DOMAIN_MTHDS, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library = get_library_manager().get_current_library()

            with pytest.raises(PipeNotFoundError):
                library.pipe_library.get_required_pipe("analytics.compute_score")
