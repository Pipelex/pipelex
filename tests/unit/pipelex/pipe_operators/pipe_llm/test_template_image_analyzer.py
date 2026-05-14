"""Tests for TemplateImageAnalyzer service."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.pipe_operators.llm.image_reference import ImageReferenceKind
from pipelex.pipe_operators.llm.template_image_analyzer import (
    TemplateImageAnalyzer,
    UnusedInputError,
    WithImagesFilterError,
)


class TestTemplateImageAnalyzer:
    """Tests for TemplateImageAnalyzer.analyze_template_for_images()."""

    # --------------------------------------------------------------------------
    # Direct Image References
    # --------------------------------------------------------------------------

    def test_single_image_variable_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that a single Image variable creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Describe this image:\n@image",
            input_specs={"image": "Image"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "image"
        assert result[0].kind == ImageReferenceKind.DIRECT
        assert result[0].nested_image_paths is None

    def test_nested_path_to_image_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that a nested path to an Image field creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Look at this:\n@page.page_view",
            input_specs={"page": "Page"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "page.page_view"
        assert result[0].kind == ImageReferenceKind.DIRECT

    def test_image_list_input_creates_direct_list_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] input creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Analyze these images: $images",
            input_specs={"images": "Image[]"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "images"
        assert result[0].kind == ImageReferenceKind.DIRECT_LIST

    def test_multiple_direct_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test multiple direct image references in same template."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Compare:\n@image_a\nwith:\n@image_b",
            input_specs={"image_a": "Image", "image_b": "Image"},
            domain_code="test_pipes",
        )

        assert len(result) == 2
        paths = {ref.variable_path for ref in result}
        assert paths == {"image_a", "image_b"}
        for ref in result:
            assert ref.kind == ImageReferenceKind.DIRECT

    # --------------------------------------------------------------------------
    # Nested References (with_images filter)
    # --------------------------------------------------------------------------

    def test_struct_with_filter_creates_nested_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that struct with | with_images filter creates NESTED reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Describe: {{ page | with_images }}",
            input_specs={"page": "Page"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "page"
        assert result[0].kind == ImageReferenceKind.NESTED
        assert result[0].nested_image_paths is not None

    def test_nested_reference_includes_image_paths(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that NESTED reference includes the paths to nested images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="{{ page | with_images }}",
            input_specs={"page": "Page"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        nested_paths = result[0].nested_image_paths
        assert nested_paths is not None
        # Page has text_and_images.images and page_view fields
        assert "page_view" in nested_paths
        assert "text_and_images.images" in nested_paths

    # --------------------------------------------------------------------------
    # No Images Cases
    # --------------------------------------------------------------------------

    def test_struct_without_filter_no_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that struct without | with_images filter does NOT create reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Describe the page:\n@page",
            input_specs={"page": "Page"},
            domain_code="test_pipes",
        )

        # No image references - page has nested images but no filter
        assert len(result) == 0

    def test_plain_text_variable_no_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that plain Text variable does NOT create image reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Process this:\n@text",
            input_specs={"text": "Text"},
            domain_code="test_pipes",
        )

        assert len(result) == 0

    def test_template_without_image_inputs(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test template with no image-related inputs."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Hello $name, your age is $age",
            input_specs={"name": "Text", "age": "Text"},
            domain_code="test_pipes",
        )

        assert len(result) == 0

    # --------------------------------------------------------------------------
    # Template Syntax Variations
    # --------------------------------------------------------------------------

    def test_dollar_syntax_image(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test $variable syntax for image."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Look at: $portrait",
            input_specs={"portrait": "Image"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].kind == ImageReferenceKind.DIRECT

    def test_at_syntax_image(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test @variable syntax for image."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Look at:\n@portrait",
            input_specs={"portrait": "Image"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].kind == ImageReferenceKind.DIRECT

    def test_jinja2_syntax_image(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test {{ variable }} Jinja2 syntax for image."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Look at: {{ portrait }}",
            input_specs={"portrait": "Image"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].kind == ImageReferenceKind.DIRECT

    # --------------------------------------------------------------------------
    # Validation Errors
    # --------------------------------------------------------------------------

    def test_with_images_on_non_image_struct_raises(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that | with_images on type without nested images raises error."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        with pytest.raises(WithImagesFilterError, match="with_images"):
            TemplateImageAnalyzer.analyze_template_for_images(
                template_source="{{ text | with_images }}",
                input_specs={"text": "Text"},
                domain_code="test_pipes",
            )

    def test_with_images_on_image_raises(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that | with_images on Image type raises error (no nesting)."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        with pytest.raises(WithImagesFilterError):
            TemplateImageAnalyzer.analyze_template_for_images(
                template_source="{{ image | with_images }}",
                input_specs={"image": "Image"},
                domain_code="test_pipes",
            )

    # --------------------------------------------------------------------------
    # Mixed References
    # --------------------------------------------------------------------------

    def test_direct_and_nested_combined(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test template with both direct image and nested image references."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Compare:\n@extra_photo\nwith {{ page | with_images }}",
            input_specs={"extra_photo": "Image", "page": "Page"},
            domain_code="test_pipes",
        )

        assert len(result) == 2
        kinds = {ref.kind for ref in result}
        assert kinds == {ImageReferenceKind.DIRECT, ImageReferenceKind.NESTED}


class TestValidateUnusedInputs:
    """Tests for TemplateImageAnalyzer.validate_unused_inputs()."""

    def test_all_inputs_used_passes(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that validation passes when all inputs are used."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Should not raise
        TemplateImageAnalyzer.validate_unused_inputs(
            template_sources=["Process $name and $age"],
            input_specs={"name": "Text", "age": "Text"},
        )

    def test_unused_input_raises(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that unused input raises error."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        with pytest.raises(UnusedInputError, match="unused_var"):
            TemplateImageAnalyzer.validate_unused_inputs(
                template_sources=["Process $name"],
                input_specs={"name": "Text", "unused_var": "Text"},
            )

    def test_input_used_in_second_template_passes(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that input used in any template passes validation."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # name in first, age in second - both should pass
        TemplateImageAnalyzer.validate_unused_inputs(
            template_sources=["Hello $name", "You are $age years old"],
            input_specs={"name": "Text", "age": "Text"},
        )

    def test_nested_path_counts_as_used(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that nested path usage counts the root variable as used."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # page.page_view should count page as used
        TemplateImageAnalyzer.validate_unused_inputs(
            template_sources=["Look at $page.page_view"],
            input_specs={"page": "Page"},
        )
