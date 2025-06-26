from pipelex.core.concept_library import ConceptLibrary
from pipelex.core.concept_native import NativeConcept


class TestConceptLibraryIsNativeConcept:
    """Test ConceptLibrary.is_native_concept method."""

    def test_is_native_concept_with_native_domain_prefix_true(self):
        """Test concept strings with native domain prefix return True."""
        concept_library = ConceptLibrary()

        # Test with various native concepts that have explicit domain
        assert concept_library.is_native_concept("native.Text") is True
        assert concept_library.is_native_concept("native.Image") is True
        assert concept_library.is_native_concept("native.PDF") is True
        assert concept_library.is_native_concept("native.Number") is True
        assert concept_library.is_native_concept("native.Dynamic") is True
        assert concept_library.is_native_concept("native.LlmPrompt") is True
        assert concept_library.is_native_concept("native.TextAndImages") is True
        assert concept_library.is_native_concept("native.Page") is True
        assert concept_library.is_native_concept("native.Anything") is True

    def test_is_native_concept_with_non_native_domain_prefix_false(self):
        """Test concept strings with non-native domain prefix return False."""
        concept_library = ConceptLibrary()

        # Test with various non-native domains
        assert concept_library.is_native_concept("custom.Text") is False
        assert concept_library.is_native_concept("documents.Page") is False
        assert concept_library.is_native_concept("images.Photo") is False
        assert concept_library.is_native_concept("test_domain.TestConcept") is False
        assert concept_library.is_native_concept("my_domain.MyClass") is False

    def test_is_native_concept_without_domain_native_concept_names_true(self):
        """Test concept strings without domain that are native concept names return True."""
        concept_library = ConceptLibrary()

        # Test all native concept names without domain
        native_names = NativeConcept.names()
        for native_name in native_names:
            assert concept_library.is_native_concept(native_name) is True, f"Failed for native concept: {native_name}"

    def test_is_native_concept_without_domain_non_native_names_false(self):
        """Test concept strings without domain that are not native concept names return False."""
        concept_library = ConceptLibrary()

        # Test various non-native concept names without domain
        assert concept_library.is_native_concept("CustomConcept") is False
        assert concept_library.is_native_concept("MyClass") is False
        assert concept_library.is_native_concept("Document") is False
        assert concept_library.is_native_concept("Photo") is False
        assert concept_library.is_native_concept("UnknownConcept") is False

    def test_is_native_concept_empty_string(self):
        """Test empty string returns False."""
        concept_library = ConceptLibrary()

        assert concept_library.is_native_concept("") is False

    def test_is_native_concept_invalid_domain_format(self):
        """Test concept strings with invalid domain format (multiple dots)."""
        concept_library = ConceptLibrary()

        # These should be handled by the concept_str_contains_domain check
        # Multiple dots should not be considered as having a domain
        assert concept_library.is_native_concept("domain.concept.subconcept") is False
        assert concept_library.is_native_concept("a.b.c.d") is False

    def test_is_native_concept_just_dot(self):
        """Test concept string that is just a dot."""
        concept_library = ConceptLibrary()

        assert concept_library.is_native_concept(".") is False

    def test_is_native_concept_dot_at_start_or_end(self):
        """Test concept strings with dot at start or end."""
        concept_library = ConceptLibrary()

        # .Text has domain="" and concept="Text", so domain != "native" -> False
        assert concept_library.is_native_concept(".Text") is False
        # Text. has domain="Text" and concept="", so domain != "native" -> False
        assert concept_library.is_native_concept("Text.") is False
        # .native has domain="" and concept="native", so domain != "native" -> False
        assert concept_library.is_native_concept(".native") is False
        # native. has domain="native" and concept="", so domain == "native" -> True
        assert concept_library.is_native_concept("native.") is True

    def test_is_native_concept_case_sensitivity(self):
        """Test that the function is case sensitive for domain checking."""
        concept_library = ConceptLibrary()

        # Test case variations of native domain
        assert concept_library.is_native_concept("Native.Text") is False  # Capital N
        assert concept_library.is_native_concept("NATIVE.Text") is False  # All caps
        # The concept part doesn't matter for domain validation, only the domain part matters
        assert concept_library.is_native_concept("native.text") is True  # lowercase concept but native domain

        # Test case variations of native concept names without domain
        assert concept_library.is_native_concept("text") is False  # lowercase
        assert concept_library.is_native_concept("TEXT") is False  # uppercase
        assert concept_library.is_native_concept("image") is False  # lowercase

    def test_is_native_concept_whitespace(self):
        """Test concept strings with whitespace."""
        concept_library = ConceptLibrary()

        # Whitespace in concept names without domain should make it invalid (not in NativeConcept.names())
        assert concept_library.is_native_concept(" Text") is False
        assert concept_library.is_native_concept("Text ") is False
        # Whitespace in domain part should make it invalid
        assert concept_library.is_native_concept(" native.Text") is False
        # Whitespace in concept part doesn't matter for domain validation, only domain matters
        assert concept_library.is_native_concept("native.Text ") is True
        assert concept_library.is_native_concept("native .Text") is False  # whitespace in domain
        assert concept_library.is_native_concept("native. Text") is True  # whitespace in concept part

    def test_is_native_concept_special_characters(self):
        """Test concept strings with special characters."""
        concept_library = ConceptLibrary()

        # Special characters should make it invalid
        assert concept_library.is_native_concept("native-Text") is False
        assert concept_library.is_native_concept("native_Text") is False
        assert concept_library.is_native_concept("native/Text") is False
        assert concept_library.is_native_concept("native\\Text") is False

    def test_native_concept_names_consistency(self):
        """Test that the function uses the correct native concept names."""
        concept_library = ConceptLibrary()

        # Get the actual native concept names
        native_names = NativeConcept.names()

        # Verify some expected names are present
        expected_names = ["Text", "Image", "PDF", "Number", "Dynamic", "LlmPrompt", "TextAndImages", "Page", "Anything"]
        for expected_name in expected_names:
            assert expected_name in native_names, f"Expected native concept name {expected_name} not found"
            # Test that each expected name returns True
            assert concept_library.is_native_concept(expected_name) is True

    def test_is_native_concept_common_examples(self):
        """Test that common native concept names work without domain prefix."""
        concept_library = ConceptLibrary()

        # Test the most commonly used native concept names
        common_native_concepts = ["Text", "Image", "PDF", "Number", "Dynamic"]

        for concept_name in common_native_concepts:
            # These should return True without needing "native." prefix
            assert concept_library.is_native_concept(concept_name) is True, f"'{concept_name}' should be recognized as native concept"

            # And they should also work with the explicit "native." prefix
            assert concept_library.is_native_concept(f"native.{concept_name}") is True, (
                f"'native.{concept_name}' should also be recognized as native concept"
            )
