from pipelex.core.concepts.validation import is_concept_ref_or_code_valid, is_concept_ref_valid


class TestConceptValidationCrossPackage:
    """Tests for cross-package concept reference validation."""

    def test_cross_package_concept_ref_is_valid(self):
        """Cross-package concept ref 'alias->domain.Code' should be valid."""
        assert is_concept_ref_valid("scoring_lib->scoring.WeightedScore") is True

    def test_cross_package_concept_ref_hierarchical_domain(self):
        """Cross-package concept ref with hierarchical domain is valid."""
        assert is_concept_ref_valid("my_lib->legal.contracts.NonCompeteClause") is True

    def test_cross_package_concept_ref_invalid_concept_code(self):
        """Cross-package concept ref with invalid concept code is invalid."""
        assert is_concept_ref_valid("my_lib->scoring.bad_code") is False

    def test_cross_package_concept_ref_no_domain(self):
        """Cross-package concept ref without domain is invalid (bare code after ->)."""
        assert is_concept_ref_valid("my_lib->WeightedScore") is False

    def test_cross_package_concept_ref_or_code_is_valid(self):
        """Cross-package refs pass is_concept_ref_or_code_valid."""
        assert is_concept_ref_or_code_valid("scoring_lib->scoring.WeightedScore") is True

    def test_cross_package_concept_ref_or_code_bare_code(self):
        """Cross-package ref with bare code after -> (no domain) passes if code is PascalCase."""
        # "alias->Code" has no dot in remainder, so it's treated as a bare code
        assert is_concept_ref_or_code_valid("my_lib->WeightedScore") is True

    def test_regular_concept_ref_still_valid(self):
        """Regular concept refs still work."""
        assert is_concept_ref_valid("scoring.WeightedScore") is True
        assert is_concept_ref_or_code_valid("WeightedScore") is True
