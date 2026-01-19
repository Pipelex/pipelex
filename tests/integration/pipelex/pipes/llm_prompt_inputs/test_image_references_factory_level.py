"""Integration tests for ImageReference creation at factory level."""

from pathlib import Path
from typing import Callable

from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.image_reference import ImageReferenceKind
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestImageReferencesFactoryLevel:
    """Tests for ImageReference creation at factory time (PipeFactory.make_from_blueprint)."""

    def test_direct_image_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image input creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT reference",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_image_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT
        assert ref.variable_path == "image"

    def test_image_list_creates_direct_list_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] input creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT_LIST reference",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="Analyze: $images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_list_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_image_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT_LIST
        assert ref.variable_path == "images"

    def test_nested_image_without_filter_no_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that struct with nested images WITHOUT | with_images creates NO reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test no reference without filter",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe the page: @page",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_reference",
            blueprint=pipe_llm_blueprint,
        )

        # Without | with_images filter, no images should be included
        assert pipe_llm.llm_prompt_spec.user_image_references is None

    def test_nested_image_with_filter_creates_nested_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that struct with | with_images creates a NESTED reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test NESTED reference",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe: {{ page | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_nested_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_image_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_image_references[0]
        assert ref.kind == ImageReferenceKind.NESTED
        assert ref.variable_path == "page"

    def test_nested_reference_has_correct_image_paths(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that NESTED reference includes correct nested_image_paths."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test nested paths",
            inputs={"page": "Page"},
            output="Text",
            prompt="{{ page | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_nested_paths",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_image_references is not None
        ref = pipe_llm.llm_prompt_spec.user_image_references[0]
        assert ref.nested_image_paths is not None
        assert "text_and_images.images" in ref.nested_image_paths
        assert "page_view" in ref.nested_image_paths
