"""Tests for ConceptFactory._make_refines method."""

from typing import List

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory

from .data import TestCases


class TestConceptFactoryMakeRefines:
    """Test ConceptFactory._make_refines method with various refines configurations."""

    @pytest.mark.parametrize(
        "test_name,blueprint,expected_result",
        TestCases.TEST_CASES,
    )
    def test_make_refines(
        self,
        test_name: str,
        blueprint: ConceptBlueprint,
        expected_result: List[str],
    ):
        """Test _make_refines method with different blueprint configurations."""
        result = ConceptFactory.make_refines(domain="test_domain", blueprint=blueprint)
        assert result == expected_result, f"Failed for test case: {test_name}"
