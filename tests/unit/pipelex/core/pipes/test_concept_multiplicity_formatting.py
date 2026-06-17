"""Unit tests for concept code formatting with multiplicity notation."""

import pytest

from pipelex.core.pipes.variable_multiplicity import format_concept_with_multiplicity


class TestFormatConceptWithMultiplicity:
    """Test the format_concept_with_multiplicity helper function."""

    @pytest.mark.parametrize(
        ("concept_code", "multiplicity", "expected"),
        [
            # Simple concepts - no multiplicity
            ("Text", None, "Text"),
            ("ConceptName", None, "ConceptName"),
            # Simple concepts - variable length
            ("Text", True, "Text[]"),
            ("Invoice", True, "Invoice[]"),
            # Simple concepts - fixed length
            ("Text", 3, "Text[3]"),
            ("Image", 1, "Image[1]"),
            ("Document", 10, "Document[10]"),
            # Domain-qualified concepts
            ("domain.Text", None, "domain.Text"),
            ("domain.Text", True, "domain.Text[]"),
            ("domain.Text", 5, "domain.Text[5]"),
            ("expense.Invoice", None, "expense.Invoice"),
            ("expense.Invoice", True, "expense.Invoice[]"),
            ("expense.Invoice", 10, "expense.Invoice[10]"),
            # Edge cases - underscores, numbers
            ("my_concept", None, "my_concept"),
            ("my_concept", True, "my_concept[]"),
            ("my_domain.MyConcept", 5, "my_domain.MyConcept[5]"),
            ("Concept123", 2, "Concept123[2]"),
            # Edge cases - zero and large numbers
            ("Text", 0, "Text[0]"),
            ("Text", 999, "Text[999]"),
        ],
    )
    def test_format_concept_with_multiplicity(self, concept_code: str, multiplicity: int | bool | None, expected: str):
        """Test formatting concept codes with all multiplicity variations."""
        assert format_concept_with_multiplicity(concept_code, multiplicity=multiplicity) == expected
