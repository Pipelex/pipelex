from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_native import NativeConcept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract


class Testget_concept_providerIsNativeConcept:
    """Test get_concept_provider.is_native_concept method."""

    def test_is_native_concept_with_native_domain_prefix_true(self):
        """Test concept strings with native domain prefix return True."""
        # Test with various native concepts that have explicit domain
        assert Concept.is_native_concept("native.Text") is True
        assert Concept.is_native_concept("native.Image") is True
        assert Concept.is_native_concept("native.PDF") is True
        assert Concept.is_native_concept("native.Number") is True
        assert Concept.is_native_concept("native.Dynamic") is True
        assert Concept.is_native_concept("native.LlmPrompt") is True
        assert Concept.is_native_concept("native.TextAndImages") is True
        assert Concept.is_native_concept("native.Page") is True
        assert Concept.is_native_concept("native.Anything") is True

    def test_is_native_concept_with_non_native_domain_prefix_false(self):
        """Test concept strings with non-native domain prefix return False."""

        # Test with various non-native domains
        assert Concept.is_native_concept("custom.Text") is False
        assert Concept.is_native_concept("documents.Page") is False
        assert Concept.is_native_concept("images.Photo") is False
        assert Concept.is_native_concept("test_domain.TestConcept") is False
        assert Concept.is_native_concept("my_domain.MyClass") is False

    def test_is_native_concept_without_domain_native_concept_names_true(self):
        """Test concept strings without domain that are native concept names return True."""
        # Test all native concept names without domain
        native_names = NativeConcept.names()
        for native_name in native_names:
            assert Concept.is_native_concept(native_name) is True, f"Failed for native concept: {native_name}"

    def test_is_native_concept_without_domain_non_native_names_false(self):
        """Test concept strings without domain that are not native concept names return False."""
        # Test various non-native concept names without domain
        assert Concept.is_native_concept("CustomConcept") is False
        assert Concept.is_native_concept("MyClass") is False
        assert Concept.is_native_concept("Document") is False
        assert Concept.is_native_concept("Photo") is False
        assert Concept.is_native_concept("UnknownConcept") is False

    def test_is_native_concept_empty_string(self):
        """Test empty string returns False."""
        assert Concept.is_native_concept("") is False

    def test_is_native_concept_invalid_domain_format(self):
        """Test concept strings with invalid domain format (multiple dots)."""
        # These should be handled by the concept_str_contains_domain check
        # Multiple dots should not be considered as having a domain
        assert Concept.is_native_concept("domain.concept.subconcept") is False
        assert Concept.is_native_concept("a.b.c.d") is False

    def test_is_native_concept_just_dot(self):
        """Test concept string that is just a dot."""
        assert Concept.is_native_concept(".") is False

    def test_is_native_concept_dot_at_start_or_end(self):
        """Test concept strings with dot at start or end."""
        # .Text has domain="" and concept="Text", so domain != "native" -> False
        assert Concept.is_native_concept(".Text") is False
        # Text. has domain="Text" and concept="", so domain != "native" -> False
        assert Concept.is_native_concept("Text.") is False
        # .native has domain="" and concept="native", so domain != "native" -> False
        assert Concept.is_native_concept(".native") is False
        # native. has domain="native" and concept="", so domain == "native" -> True
        assert Concept.is_native_concept("native.") is True

    def test_is_native_concept_case_sensitivity(self):
        """Test that the function is case sensitive for domain checking."""
        # Test case variations of native domain
        assert Concept.is_native_concept("Native.Text") is False  # Capital N
        assert Concept.is_native_concept("NATIVE.Text") is False  # All caps
        # The concept part doesn't matter for domain validation, only the domain part matters
        assert Concept.is_native_concept("native.text") is True  # lowercase concept but native domain

        # Test case variations of native concept names without domain
        assert Concept.is_native_concept("text") is False  # lowercase
        assert Concept.is_native_concept("TEXT") is False  # uppercase
        assert Concept.is_native_concept("image") is False  # lowercase

    def test_is_native_concept_whitespace(self):
        """Test concept strings with whitespace."""
        # Whitespace in concept names without domain should make it invalid (not in NativeConcept.names())
        assert Concept.is_native_concept(" Text") is False
        assert Concept.is_native_concept("Text ") is False
        # Whitespace in domain part should make it invalid
        assert Concept.is_native_concept(" native.Text") is False
        # Whitespace in concept part doesn't matter for domain validation, only domain matters
        assert Concept.is_native_concept("native.Text ") is True
        assert Concept.is_native_concept("native .Text") is False  # whitespace in domain
        assert Concept.is_native_concept("native. Text") is True  # whitespace in concept part

    def test_is_native_concept_special_characters(self):
        """Test concept strings with special characters."""
        # Special characters should make it invalid
        assert Concept.is_native_concept("native-Text") is False
        assert Concept.is_native_concept("native_Text") is False
        assert Concept.is_native_concept("native/Text") is False
        assert Concept.is_native_concept("native\\Text") is False

    def test_native_concept_names_consistency(self):
        """Test that the function uses the correct native concept names."""

        # Get the actual native concept names
        native_names = NativeConcept.names()

        # Verify some expected names are present
        expected_names = ["Text", "Image", "PDF", "Number", "Dynamic", "LlmPrompt", "TextAndImages", "Page", "Anything"]
        for expected_name in expected_names:
            assert expected_name in native_names, f"Expected native concept name {expected_name} not found"
            # Test that each expected name returns True
            assert Concept.is_native_concept(expected_name) is True

    def test_is_native_concept_common_examples(self):
        """Test that common native concept names work without domain prefix."""

        # Test the most commonly used native concept names
        common_native_concepts = ["Text", "Image", "PDF", "Number", "Dynamic"]

        for concept_name in common_native_concepts:
            # These should return True without needing "native." prefix
            assert Concept.is_native_concept(concept_name) is True, f"'{concept_name}' should be recognized as native concept"

            # And they should also work with the explicit "native." prefix
            assert Concept.is_native_concept(f"native.{concept_name}") is True, f"'native.{concept_name}' should also be recognized as native concept"


class TestConceptLibraryCompatibility:
    """Test ConceptLibrary compatibility methods."""

    def test_is_compatible_by_concept_code_simple_text_concept_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that SimpleTextConcept (no structure) is compatible with native Text."""
        # Test: SimpleTextConcept should be compatible with native Text (defaults to Text)
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.SimpleTextConcept", wanted_concept_code="native.Text"
        )
        assert result is True, "SimpleTextConcept should be compatible with native Text"

    def test_is_compatible_by_concept_code_fundamentals_doc_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that FundamentalsDoc (custom structure) is not compatible with native Text."""
        # Test: FundamentalsDoc should NOT be compatible with native Text (has custom structure)
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.FundamentalsDoc", wanted_concept_code="native.Text"
        )
        assert result is False, "FundamentalsDoc should not be compatible with native Text"

    def test_is_compatible_by_concept_code_explicit_text_concept_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that ExplicitTextConcept (explicitly refines Text) is compatible with native Text."""
        # Test: ExplicitTextConcept should be compatible with native Text
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.ExplicitTextConcept", wanted_concept_code="native.Text"
        )
        assert result is True, "ExplicitTextConcept should be compatible with native Text"

    def test_is_compatible_by_concept_code_image_based_concept_vs_image(self, concept_provider: ConceptProviderAbstract):
        """Test that ImageBasedConcept is compatible with native Image."""
        # Test: ImageBasedConcept should be compatible with native Image
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.ImageBasedConcept", wanted_concept_code="native.Image"
        )
        assert result is True, "ImageBasedConcept should be compatible with native Image"

    def test_is_compatible_by_concept_code_image_based_concept_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that ImageBasedConcept is not compatible with native Text."""
        # Test: ImageBasedConcept should NOT be compatible with native Text
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.ImageBasedConcept", wanted_concept_code="native.Text"
        )
        assert result is False, "ImageBasedConcept should not be compatible with native Text"

    def test_is_compatible_by_concept_code_documentation_concept_vs_fundamentals_doc(self, concept_provider: ConceptProviderAbstract):
        """Test that DocumentationConcept is compatible with FundamentalsDoc."""
        # Test: DocumentationConcept should be compatible with FundamentalsDoc
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.DocumentationConcept", wanted_concept_code="concept_library_tests.FundamentalsDoc"
        )
        assert result is True, "DocumentationConcept should be compatible with FundamentalsDoc"

    def test_is_compatible_by_concept_code_specialized_doc_vs_fundamentals_doc(self, concept_provider: ConceptProviderAbstract):
        """Test that SpecializedDoc is compatible with FundamentalsDoc."""
        # Test: SpecializedDoc should be compatible with FundamentalsDoc
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.SpecializedDoc", wanted_concept_code="concept_library_tests.FundamentalsDoc"
        )
        assert result is True, "SpecializedDoc should be compatible with FundamentalsDoc"

    def test_is_compatible_by_concept_code_multimedia_concept_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that MultiMediaConcept is compatible with Text (multiple inheritance)."""
        # Test: MultiMediaConcept should be compatible with Text
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.MultiMediaConcept", wanted_concept_code="native.Text"
        )
        assert result is True, "MultiMediaConcept should be compatible with Text"

    def test_is_compatible_by_concept_code_multimedia_concept_vs_image(self, concept_provider: ConceptProviderAbstract):
        """Test that MultiMediaConcept is compatible with Image (multiple inheritance)."""
        # Test: MultiMediaConcept should be compatible with Image
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.MultiMediaConcept", wanted_concept_code="native.Image"
        )
        assert result is True, "MultiMediaConcept should be compatible with Image"

    def test_is_compatible_by_concept_code_independent_concept_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that IndependentConcept is not compatible with Text."""
        # Test: IndependentConcept should NOT be compatible with Text (no refines)
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.IndependentConcept", wanted_concept_code="native.Text"
        )
        assert result is False, "IndependentConcept should not be compatible with Text"

    def test_is_compatible_by_concept_code_derived_text_concept_vs_text(self, concept_provider: ConceptProviderAbstract):
        """Test that DerivedTextConcept is compatible with Text (inheritance chain)."""
        # Test: DerivedTextConcept should be compatible with Text (through ExplicitTextConcept)
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.DerivedTextConcept", wanted_concept_code="native.Text"
        )
        assert result is True, "DerivedTextConcept should be compatible with Text through inheritance chain"

    def test_is_compatible_by_concept_code_derived_text_concept_vs_explicit_text(self, concept_provider: ConceptProviderAbstract):
        """Test that DerivedTextConcept is compatible with ExplicitTextConcept (direct inheritance)."""
        # Test: DerivedTextConcept should be compatible with ExplicitTextConcept
        result = concept_provider.is_compatible_by_concept_code(
            tested_concept_code="concept_library_tests.DerivedTextConcept", wanted_concept_code="concept_library_tests.ExplicitTextConcept"
        )
        assert result is True, "DerivedTextConcept should be compatible with ExplicitTextConcept"
