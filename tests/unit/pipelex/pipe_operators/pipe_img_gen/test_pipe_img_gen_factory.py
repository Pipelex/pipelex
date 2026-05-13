"""Tests for PipeImgGenFactory image reference detection."""

from pathlib import Path
from typing import Callable

from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.shared.image_reference import ImageReferenceKind


class TestPipeImgGenFactoryImageReferences:
    """Tests for image reference detection in PipeImgGenFactory."""

    def test_image_ref_in_positive_prompt_only(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that image refs in positive prompt are detected."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test image in positive prompt",
            inputs={"source_image": "Image"},
            output="Image",
            prompt="Edit this image:\n@source_image",
            negative_prompt=None,
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_positive_only",
            blueprint=blueprint,
        )

        # Verify image reference was detected
        image_refs = pipe.img_gen_prompt_blueprint.image_references
        assert image_refs is not None
        assert len(image_refs) == 1
        assert image_refs[0].variable_path == "source_image"
        assert image_refs[0].kind == ImageReferenceKind.DIRECT

    def test_image_ref_in_negative_prompt_only(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that image refs in negative prompt are detected.

        This is the key fix: the factory must analyze negative_prompt for image references.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test image in negative prompt",
            inputs={"avoid_image": "Image"},
            output="Image",
            prompt="Generate a beautiful landscape",
            negative_prompt="Avoid features from:\n@avoid_image",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_negative_only",
            blueprint=blueprint,
        )

        # Verify image reference was detected from negative prompt
        image_refs = pipe.img_gen_prompt_blueprint.image_references
        assert image_refs is not None, "Image references should be detected in negative prompt"
        assert len(image_refs) == 1
        assert image_refs[0].variable_path == "avoid_image"
        assert image_refs[0].kind == ImageReferenceKind.DIRECT

    def test_image_refs_in_both_prompts_are_merged(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that image refs from both prompts are merged."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test images in both prompts",
            inputs={"style_ref": "Image", "avoid_ref": "Image"},
            output="Image",
            prompt="Apply style from:\n@style_ref",
            negative_prompt="Avoid style from:\n@avoid_ref",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_both_prompts",
            blueprint=blueprint,
        )

        # Verify both image references were detected
        image_refs = pipe.img_gen_prompt_blueprint.image_references
        assert image_refs is not None
        assert len(image_refs) == 2
        paths = {ref.variable_path for ref in image_refs}
        assert paths == {"style_ref", "avoid_ref"}

    def test_same_image_in_both_prompts_is_deduplicated(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that same image ref in both prompts appears only once."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test same image in both prompts",
            inputs={"shared_image": "Image"},
            output="Image",
            prompt="Apply style from:\n@shared_image",
            negative_prompt="But avoid these aspects:\n@shared_image",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_deduplicated",
            blueprint=blueprint,
        )

        # Verify image reference appears only once (deduplicated)
        image_refs = pipe.img_gen_prompt_blueprint.image_references
        assert image_refs is not None
        assert len(image_refs) == 1
        assert image_refs[0].variable_path == "shared_image"

    def test_image_list_in_negative_prompt(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that image list refs in negative prompt are detected."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test image list in negative prompt",
            inputs={"avoid_images": "Image[]"},
            output="Image",
            prompt="Generate a beautiful landscape",
            negative_prompt="Avoid features from:\n@avoid_images",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_negative_list",
            blueprint=blueprint,
        )

        # Verify image list reference was detected from negative prompt
        image_refs = pipe.img_gen_prompt_blueprint.image_references
        assert image_refs is not None
        assert len(image_refs) == 1
        assert image_refs[0].variable_path == "avoid_images"
        assert image_refs[0].kind == ImageReferenceKind.DIRECT_LIST
