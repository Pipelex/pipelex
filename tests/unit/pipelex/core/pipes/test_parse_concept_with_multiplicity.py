import pytest

from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity


class TestParseConceptWithMultiplicity:
    """Test parsing of concept specifications with bracket notation."""

    def test_valid_simple_concept(self):
        """Test parsing simple concept names without brackets."""
        result = parse_concept_with_multiplicity("Text")
        assert result.concept == "Text"
        assert result.multiplicity is None

    def test_valid_concept_with_variable_list(self):
        """Test parsing concept with empty brackets []."""
        result = parse_concept_with_multiplicity("Text[]")
        assert result.concept == "Text"
        assert result.multiplicity is True

    def test_valid_concept_with_fixed_count(self):
        """Test parsing concept with fixed count [N]."""
        result = parse_concept_with_multiplicity("Text[5]")
        assert result.concept == "Text"
        assert result.multiplicity == 5

    def test_valid_domain_qualified_concept(self):
        """Test parsing domain-qualified concepts."""
        result = parse_concept_with_multiplicity("domain.Concept")
        assert result.concept == "domain.Concept"
        assert result.multiplicity is None

    def test_valid_domain_qualified_with_brackets(self):
        """Test parsing domain-qualified concepts with brackets."""
        result = parse_concept_with_multiplicity("native.Text[]")
        assert result.concept == "native.Text"
        assert result.multiplicity is True

        result = parse_concept_with_multiplicity("custom.Item[3]")
        assert result.concept == "custom.Item"
        assert result.multiplicity == 3

    def test_invalid_syntax_starting_with_number(self):
        """Test that concepts starting with numbers are rejected."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("123Invalid[]")

    def test_invalid_syntax_with_hyphen(self):
        """Test that concepts with hyphens are rejected."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("foo-bar[2]")

    def test_invalid_syntax_with_special_chars(self):
        """Test that concepts with special characters are rejected."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("!@#$%")

    def test_invalid_syntax_empty_string(self):
        """Test that empty string is rejected."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("")

    def test_invalid_syntax_only_brackets(self):
        """Test that only brackets without concept is rejected."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("[]")

    def test_concepts_starting_with_underscore(self):
        """Test that concepts starting with underscore are valid."""
        result = parse_concept_with_multiplicity("_PrivateConcept")
        assert result.concept == "_PrivateConcept"
        assert result.multiplicity is None

        result = parse_concept_with_multiplicity("_internal.Data[]")
        assert result.concept == "_internal.Data"
        assert result.multiplicity is True
