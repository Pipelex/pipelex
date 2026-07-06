import pytest

from pipelex.core.pipes.variable_multiplicity import PresenceMarker, parse_concept_with_multiplicity


class TestParseConceptWithMultiplicity:
    """Test parsing of concept specifications with bracket notation."""

    def test_valid_simple_concept(self):
        """Test parsing simple concept names without brackets."""
        result = parse_concept_with_multiplicity("Text")
        assert result.concept_ref_or_code == "Text"
        assert result.multiplicity is None

    def test_valid_concept_with_variable_list(self):
        """Test parsing concept with empty brackets []."""
        result = parse_concept_with_multiplicity("Text[]")
        assert result.concept_ref_or_code == "Text"
        assert result.multiplicity is True

    def test_valid_concept_with_fixed_count(self):
        """Test parsing concept with fixed count [N]."""
        result = parse_concept_with_multiplicity("Text[5]")
        assert result.concept_ref_or_code == "Text"
        assert result.multiplicity == 5

    def test_valid_domain_qualified_concept(self):
        """Test parsing domain-qualified concepts."""
        result = parse_concept_with_multiplicity("domain.Concept")
        assert result.concept_ref_or_code == "domain.Concept"
        assert result.multiplicity is None

    def test_valid_domain_qualified_with_brackets(self):
        """Test parsing domain-qualified concepts with brackets."""
        result = parse_concept_with_multiplicity("native.Text[]")
        assert result.concept_ref_or_code == "native.Text"
        assert result.multiplicity is True

        result = parse_concept_with_multiplicity("custom.Item[3]")
        assert result.concept_ref_or_code == "custom.Item"
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
        assert result.concept_ref_or_code == "_PrivateConcept"
        assert result.multiplicity is None

        result = parse_concept_with_multiplicity("_internal.Data[]")
        assert result.concept_ref_or_code == "_internal.Data"
        assert result.multiplicity is True

    def test_invalid_zero_multiplicity(self):
        """Test that zero multiplicity is rejected since a pipe must produce at least one output."""
        with pytest.raises(ValueError, match="multiplicity must be at least 1"):
            parse_concept_with_multiplicity("Text[0]")

        with pytest.raises(ValueError, match="multiplicity must be at least 1"):
            parse_concept_with_multiplicity("domain.Concept[0]")

    def test_invalid_negative_multiplicity(self):
        """Test that negative multiplicity is rejected (fails regex pattern)."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("Text[-1]")

        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity("domain.Concept[-5]")

    # ========== Hierarchical domain tests ==========

    def test_valid_hierarchical_domain_concept(self):
        """Test parsing concept with hierarchical domain (multiple dot segments)."""
        result = parse_concept_with_multiplicity("legal.contracts.NonCompeteClause")
        assert result.concept_ref_or_code == "legal.contracts.NonCompeteClause"
        assert result.multiplicity is None

    def test_valid_hierarchical_domain_concept_with_variable_list(self):
        """Test parsing hierarchical domain concept with empty brackets []."""
        result = parse_concept_with_multiplicity("legal.contracts.NonCompeteClause[]")
        assert result.concept_ref_or_code == "legal.contracts.NonCompeteClause"
        assert result.multiplicity is True

    def test_valid_hierarchical_domain_concept_with_fixed_count(self):
        """Test parsing hierarchical domain concept with fixed count [N]."""
        result = parse_concept_with_multiplicity("legal.contracts.NonCompeteClause[5]")
        assert result.concept_ref_or_code == "legal.contracts.NonCompeteClause"
        assert result.multiplicity == 5

    def test_valid_deep_hierarchical_domain(self):
        """Test parsing concept with deeply nested domain."""
        result = parse_concept_with_multiplicity("a.b.c.d.Entity[]")
        assert result.concept_ref_or_code == "a.b.c.d.Entity"
        assert result.multiplicity is True

    # ========== Presence marker tests ==========

    def test_no_marker_means_plain_presence(self):
        """A spec without a presence marker parses as plain presence."""
        for spec in ["Text", "Text[]", "Text[5]", "domain.Concept"]:
            result = parse_concept_with_multiplicity(spec)
            assert result.presence == PresenceMarker.PLAIN

    @pytest.mark.parametrize(
        ("spec", "expected_concept", "expected_multiplicity", "expected_presence"),
        [
            ("Text?", "Text", None, PresenceMarker.OPTIONAL),
            ("Text!", "Text", None, PresenceMarker.FORCE),
            ("domain.Concept?", "domain.Concept", None, PresenceMarker.OPTIONAL),
            ("domain.Concept!", "domain.Concept", None, PresenceMarker.FORCE),
            ("legal.contracts.PenaltyClause?", "legal.contracts.PenaltyClause", None, PresenceMarker.OPTIONAL),
            ("_PrivateConcept?", "_PrivateConcept", None, PresenceMarker.OPTIONAL),
            # The parser accepts marker + multiplicity combinations (multiplicity then presence,
            # e.g. "X[]?"); the D1 mutual-exclusion rule is enforced at the blueprint/spec layer
            # where the context (input vs output) is known.
            ("Text[]?", "Text", True, PresenceMarker.OPTIONAL),
            ("Text[3]?", "Text", 3, PresenceMarker.OPTIONAL),
            ("Text[]!", "Text", True, PresenceMarker.FORCE),
        ],
    )
    def test_presence_marker_parsing(
        self,
        spec: str,
        expected_concept: str,
        expected_multiplicity: int | bool | None,
        expected_presence: PresenceMarker,
    ):
        """Presence markers parse alongside multiplicity."""
        result = parse_concept_with_multiplicity(spec)
        assert result.concept_ref_or_code == expected_concept
        assert result.multiplicity == expected_multiplicity
        assert result.presence == expected_presence

    @pytest.mark.parametrize(
        "spec",
        [
            "Text??",
            "Text?!",
            "Text!?",
            "Text!!",
            # Fixed order: multiplicity then presence — marker before brackets is a syntax error
            "Text?[]",
            "Text![3]",
            "?Text",
            "!Text",
            "?",
            "!",
        ],
    )
    def test_invalid_presence_marker_syntax(self, spec: str):
        """Doubled markers, marker-before-brackets, and bare markers are syntax errors."""
        with pytest.raises(ValueError, match="Invalid concept specification syntax"):
            parse_concept_with_multiplicity(spec)
