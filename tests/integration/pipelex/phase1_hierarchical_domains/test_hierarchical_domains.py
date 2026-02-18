"""E2E spec tests for Phase 1: Hierarchical Domains + Pipe Namespacing.

These tests validate actual .mthds files through the full pipeline:
interpret -> blueprint -> factory -> dry run (no inference).
"""

from pathlib import Path

import pytest

from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle, validate_bundles_from_directory

VALID_DIR = Path(__file__).parent / "valid_fixtures"
INVALID_DIR = Path(__file__).parent / "invalid_fixtures"


@pytest.mark.asyncio(loop_scope="class")
class TestHierarchicalDomainsAndPipeNamespacing:
    """E2E spec tests for hierarchical domains and pipe namespacing."""

    # ========== POSITIVE TESTS ==========

    async def test_single_segment_domain_baseline(self):
        """Single-segment domain should work as before."""
        result = await validate_bundle(
            mthds_file_path=VALID_DIR / "hierarchical_domain_single.mthds",
            library_dirs=[VALID_DIR],
        )
        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "legal"
        assert len(result.pipes) > 0

    async def test_nested_hierarchical_domain(self):
        """Nested hierarchical domain 'legal.contracts' with concepts and pipes."""
        result = await validate_bundle(
            mthds_file_path=VALID_DIR / "hierarchical_domain_nested.mthds",
            library_dirs=[VALID_DIR],
        )
        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "legal.contracts"
        assert result.blueprints[0].concept is not None
        assert "NonCompeteClause" in result.blueprints[0].concept
        assert len(result.pipes) > 0

    async def test_deep_hierarchical_domain(self):
        """Deeply nested hierarchical domain 'legal.contracts.shareholder'."""
        result = await validate_bundle(
            mthds_file_path=VALID_DIR / "hierarchical_domain_deep.mthds",
            library_dirs=[VALID_DIR],
        )
        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "legal.contracts.shareholder"
        assert len(result.pipes) > 0

    async def test_cross_domain_pipe_ref_in_sequence(self):
        """Cross-domain pipe ref 'scoring.compute_score' in a PipeSequence step."""
        result = await validate_bundle(
            mthds_file_path=VALID_DIR / "cross_domain_pipe_refs.mthds",
            library_dirs=[VALID_DIR],
        )
        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "orchestration"
        assert len(result.pipes) > 0

    async def test_cross_domain_concept_ref_with_hierarchical_domain(self):
        """Cross-domain concept ref 'legal.contracts.NonCompeteClause' as input."""
        result = await validate_bundle(
            mthds_file_path=VALID_DIR / "cross_domain_concept_refs.mthds",
            library_dirs=[VALID_DIR],
        )
        assert result is not None
        assert len(result.blueprints) == 1
        assert result.blueprints[0].domain == "analysis"
        assert len(result.pipes) > 0

    async def test_multi_bundle_directory_load(self):
        """All valid .mthds files from the fixtures directory loaded together."""
        result = await validate_bundles_from_directory(directory=VALID_DIR)
        assert result is not None
        assert len(result.blueprints) >= 6

        domain_names = {blueprint.domain for blueprint in result.blueprints}
        assert "legal" in domain_names
        assert "legal.contracts" in domain_names
        assert "legal.contracts.shareholder" in domain_names
        assert "scoring" in domain_names
        assert "orchestration" in domain_names
        assert "analysis" in domain_names

    # ========== NEGATIVE TESTS ==========

    async def test_invalid_double_dot_domain(self):
        """Domain 'legal..contracts' should raise a validation error."""
        with pytest.raises((ValidateBundleError, PipelexInterpreterError)):
            await validate_bundle(
                mthds_file_path=INVALID_DIR / "invalid_double_dot.mthds_invalid",
            )

    async def test_invalid_leading_dot_domain(self):
        """Domain '.legal' should raise a validation error."""
        with pytest.raises((ValidateBundleError, PipelexInterpreterError)):
            await validate_bundle(
                mthds_file_path=INVALID_DIR / "invalid_leading_dot.mthds_invalid",
            )

    async def test_invalid_same_domain_pipe_ref_to_nonexistent(self):
        """Same-domain pipe ref to non-existent pipe should raise error."""
        with pytest.raises((ValidateBundleError, PipelexInterpreterError)):
            await validate_bundle(
                mthds_file_path=INVALID_DIR / "invalid_same_domain_pipe_ref.mthds_invalid",
            )
