"""Unit tests for ConceptExampleGenerator."""

from pipelex.core.concepts.concept_example_generator import (
    ConceptExampleFormat,
    ConceptExampleGenerator,
    ConceptExampleGranularity,
    generate_json_example,
    generate_python_example,
)


class TestConceptExampleFormat:
    """Test the ConceptExampleFormat enum."""

    def test_enum_values(self) -> None:
        """Test that the enum has the expected values."""
        assert ConceptExampleFormat.JSON.value == "json"
        assert ConceptExampleFormat.PYTHON.value == "python"

    def test_enum_iteration(self) -> None:
        """Test that we can iterate over enum values."""
        values = list(ConceptExampleFormat)
        assert len(values) == 2
        assert ConceptExampleFormat.JSON in values
        assert ConceptExampleFormat.PYTHON in values


class TestConceptExampleGranularity:
    """Test the ConceptExampleGranularity enum."""

    def test_enum_values(self) -> None:
        """Test that the enum has the expected values."""
        assert ConceptExampleGranularity.LIGHT.value == "light"
        assert ConceptExampleGranularity.HARD.value == "hard"

    def test_enum_iteration(self) -> None:
        """Test that we can iterate over enum values."""
        values = list(ConceptExampleGranularity)
        assert len(values) == 2
        assert ConceptExampleGranularity.LIGHT in values
        assert ConceptExampleGranularity.HARD in values


class TestConceptExampleGeneratorJsonLight:
    """Test ConceptExampleGenerator with JSON format and LIGHT granularity."""

    def test_json_light_text_native(self) -> None:
        """Test JSON LIGHT format for native Text concept - should return simple string."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
        )
        # LIGHT mode: just a string
        assert result == "message_text"

    def test_json_light_number_native(self) -> None:
        """Test JSON LIGHT format for native Number concept - should return simple number."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="native.Number",
            structure_class_name="NumberContent",
            var_name="count",
        )
        # LIGHT mode: just a number
        assert result == 0

    def test_json_light_image_native(self) -> None:
        """Test JSON LIGHT format for native Image concept - should return just the URL."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="native.Image",
            structure_class_name="ImageContent",
            var_name="photo",
        )
        # LIGHT mode: just the URL string
        assert result == "photo_url"

    def test_json_light_pdf_native(self) -> None:
        """Test JSON LIGHT format for native PDF concept - should return just the URL."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="native.PDF",
            structure_class_name="PDFContent",
            var_name="document",
        )
        # LIGHT mode: just the URL string
        assert result == "document_url"


class TestConceptExampleGeneratorJsonHard:
    """Test ConceptExampleGenerator with JSON format and HARD granularity."""

    def test_json_hard_text_native(self) -> None:
        """Test JSON HARD format for native Text concept - should return full BaseModel."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.HARD)
        result = generator.generate_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
        )
        # HARD mode: full structure with concept_code
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Text"
        assert "content" in result
        assert isinstance(result["content"], dict)
        assert "text" in result["content"]

    def test_json_hard_number_native(self) -> None:
        """Test JSON HARD format for native Number concept - should return full BaseModel."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.HARD)
        result = generator.generate_example(
            concept_string="native.Number",
            structure_class_name="NumberContent",
            var_name="count",
        )
        # HARD mode: full structure with concept_code
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Number"
        assert "content" in result
        assert isinstance(result["content"], dict)
        # NumberContent has a "number" field, not "value"
        assert "number" in result["content"]

    def test_json_hard_image_native(self) -> None:
        """Test JSON HARD format for native Image concept - should return full BaseModel."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.HARD)
        result = generator.generate_example(
            concept_string="native.Image",
            structure_class_name="ImageContent",
            var_name="photo",
        )
        # HARD mode: full structure with concept_code
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Image"
        assert "content" in result
        assert isinstance(result["content"], dict)
        assert "url" in result["content"]


class TestConceptExampleGeneratorPythonLight:
    """Test ConceptExampleGenerator with Python format and LIGHT granularity."""

    def test_python_light_text_native(self) -> None:
        """Test Python LIGHT format for native Text concept - should return simple string."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.PYTHON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
        )
        # LIGHT mode: just a string
        assert result == "message_text"

    def test_python_light_image_native(self) -> None:
        """Test Python LIGHT format for native Image concept - returns Python code string."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.PYTHON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="native.Image",
            structure_class_name="ImageContent",
            var_name="photo",
        )
        # LIGHT mode: Python class instantiation as string
        assert isinstance(result, str)
        assert "ImageContent" in result
        assert 'url="photo_url"' in result


class TestConceptExampleGeneratorPythonHard:
    """Test ConceptExampleGenerator with Python format and HARD granularity."""

    def test_python_hard_text_native(self) -> None:
        """Test Python HARD format for native Text concept - should return full class instantiation."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.PYTHON, ConceptExampleGranularity.HARD)
        result = generator.generate_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
        )
        # HARD mode: full structure with concept_code and Python class instantiation
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Text"
        assert "content" in result
        # Content should be a Python code string
        content = result["content"]
        assert isinstance(content, str)
        assert "TextContent" in content
        assert "text=" in content

    def test_python_hard_image_native(self) -> None:
        """Test Python HARD format for native Image concept - should return full class instantiation."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.PYTHON, ConceptExampleGranularity.HARD)
        result = generator.generate_example(
            concept_string="native.Image",
            structure_class_name="ImageContent",
            var_name="photo",
        )
        # HARD mode: full structure with concept_code and Python class instantiation
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Image"
        assert "content" in result
        content = result["content"]
        assert isinstance(content, str)
        assert "ImageContent" in content
        assert "url=" in content


class TestConceptExampleGeneratorCustomConcept:
    """Test ConceptExampleGenerator with custom concepts."""

    def test_json_custom_concept_not_found(self) -> None:
        """Test JSON format for a custom concept when class is not found."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.LIGHT)
        result = generator.generate_example(
            concept_string="accounting.Invoice",
            structure_class_name="InvoiceContent",
            var_name="invoice",
        )
        # When class is not found, should return wrapped empty content
        assert isinstance(result, dict)
        assert result["concept_code"] == "accounting.Invoice"
        assert result["content"] == {}

    def test_json_refined_text_light(self) -> None:
        """Test JSON LIGHT format for a concept that refines Text."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.LIGHT)
        # For a non-native concept using TextContent
        result = generator.generate_example(
            concept_string="domain.Question",
            structure_class_name="TextContent",
            var_name="question",
        )
        # Should wrap with concept_code since it's not a native concept
        assert isinstance(result, dict)
        assert result["concept_code"] == "domain.Question"
        # In LIGHT mode, content is simplified
        assert result["content"] == "question_text"

    def test_json_refined_text_hard(self) -> None:
        """Test JSON HARD format for a concept that refines Text."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, ConceptExampleGranularity.HARD)
        result = generator.generate_example(
            concept_string="domain.Question",
            structure_class_name="TextContent",
            var_name="question",
        )
        # Should wrap with concept_code
        assert isinstance(result, dict)
        assert result["concept_code"] == "domain.Question"
        # In HARD mode, content is full BaseModel
        assert isinstance(result["content"], dict)
        assert "text" in result["content"]


class TestImportsTracking:
    """Test that imports_needed tracks used classes."""

    def test_json_imports_tracking(self) -> None:
        """Test that imports_needed tracks used classes in JSON mode."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.JSON)
        generator.generate_example(
            concept_string="native.Image",
            structure_class_name="ImageContent",
            var_name="photo",
        )
        assert "ImageContent" in generator.imports_needed

    def test_python_imports_tracking(self) -> None:
        """Test that imports_needed tracks used classes in Python mode."""
        generator = ConceptExampleGenerator(ConceptExampleFormat.PYTHON)
        generator.generate_example(
            concept_string="native.PDF",
            structure_class_name="PDFContent",
            var_name="doc",
        )
        assert "PDFContent" in generator.imports_needed


class TestConvenienceFunctions:
    """Test the convenience functions."""

    def test_generate_json_example_light(self) -> None:
        """Test generate_json_example convenience function with LIGHT granularity."""
        result = generate_json_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
            granularity=ConceptExampleGranularity.LIGHT,
        )
        assert result == "message_text"

    def test_generate_json_example_hard(self) -> None:
        """Test generate_json_example convenience function with HARD granularity."""
        result = generate_json_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
            granularity=ConceptExampleGranularity.HARD,
        )
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Text"
        assert "content" in result

    def test_generate_python_example_light(self) -> None:
        """Test generate_python_example convenience function with LIGHT granularity."""
        result, imports = generate_python_example(
            concept_string="native.Image",
            structure_class_name="ImageContent",
            var_name="photo",
            granularity=ConceptExampleGranularity.LIGHT,
        )
        assert isinstance(result, str)
        assert "ImageContent" in result
        assert "ImageContent" in imports

    def test_generate_python_example_hard(self) -> None:
        """Test generate_python_example convenience function with HARD granularity."""
        result, imports = generate_python_example(
            concept_string="native.Text",
            structure_class_name="TextContent",
            var_name="message",
            granularity=ConceptExampleGranularity.HARD,
        )
        assert isinstance(result, dict)
        assert "TextContent" in imports
