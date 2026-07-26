"""Regression test for a known bug: an image embedded inside a PipeCompose template
is flattened to text and never delivered to a downstream PipeImgGen.

Scenario (reported by a user):
  1. A PipeCompose builds the image-generation prompt from a template that references
     an Image via `@source_image`. Its output concept is `Text`.
  2. A PipeImgGen receives ONLY that composed prompt (`$gen_prompt`); it does not declare
     the image as a direct input.

Because `Text` is text-typed, the `@source_image` reference is rendered into a
plain URL string during composition and the live image binding is lost. The PipeImgGen
then has no image reference of its own, so the image never reaches the model: the
generator hallucinates from text alone.

`make_img_gen_prompt(...).input_images` is exactly the set of images handed to the image
model, so it is the precise observable for "was the image delivered?".

These tests do NOT fix the bug. One locks in the current (buggy) behavior; the other is an
`xfail(strict=True)` capturing the behavior we want, so it will flip to a failure the day
the bug is fixed and prompt removal of the marker.
"""

from typing import Callable, cast

import pytest

from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose, PipeComposeOutput
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

# A recognizable token in the reference image URL so we can detect when the image was
# silently degraded into prompt text.
SOURCE_IMAGE_URL = "https://example.com/secret-token-glyph-7q2x.png"


async def _compose_then_build_img_gen_prompt(job_metadata: JobMetadata) -> tuple[str, ImgGenPrompt]:
    """Run the reported chain offline and return (composed_prompt_text, img_gen_prompt).

    Step 1 — PipeCompose embeds the image in its template and outputs a Text.
    Step 2 — PipeImgGen receives only the composed prompt and builds the ImgGenPrompt that
             would be sent to the model. No model is called.
    """
    # Working memory holding the reference image.
    working_memory = WorkingMemoryFactory.make_from_single_stuff(
        stuff=StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.IMAGE),
            content=ImageContent(url=SOURCE_IMAGE_URL),
            name="source_image",
        ),
    )

    # Step 1: compose the image-gen prompt, embedding the image with `@source_image`.
    compose_blueprint = PipeComposeBlueprint(
        description="Build an image-gen prompt that embeds the reference image",
        inputs={"source_image": "Image"},
        template=TemplateBlueprint(
            template="Recreate the reference image, only change the background to crimson red.\n\nReference image:\n@source_image",
            templating_style=TemplatingStyle(tag_style=TagStyle.TICKS, text_format=TextFormat.MARKDOWN),
            category=TemplateCategory.IMG_GEN_PROMPT,
        ),
        output=NativeConceptCode.TEXT,
    )
    compose_job = PipeJobFactory.make_pipe_job(
        pipe=PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="generic",
            pipe_code="adhoc_compose_embeds_image",
            blueprint=compose_blueprint,
        ),
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=job_metadata,
        working_memory=working_memory,
    )
    compose_output = cast("PipeComposeOutput", await get_pipe_router().run(pipe_job=compose_job))
    composed_prompt_text = compose_output.main_stuff_as_str

    # Step 2: hand the composed prompt (and nothing else referencing the image) to PipeImgGen.
    working_memory.add_new_stuff(name="gen_prompt", stuff=compose_output.main_stuff)
    pipe_img_gen = PipeFactory[PipeImgGen].make_from_blueprint(
        domain_code="generic",
        pipe_code="adhoc_img_gen_from_composed_prompt",
        blueprint=PipeImgGenBlueprint(
            description="Generate from the composed prompt only — no direct image input",
            inputs={"gen_prompt": "Text"},
            output="Image",
            prompt="$gen_prompt",
        ),
    )
    img_gen_prompt = await pipe_img_gen.img_gen_prompt_blueprint.make_img_gen_prompt(context_provider=working_memory)
    return composed_prompt_text, img_gen_prompt


@pytest.mark.asyncio(loop_scope="class")
class TestComposeDropsEmbeddedImage:
    async def test_image_embedded_in_compose_is_currently_lost(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
    ) -> None:
        """BUG (current behavior): the image embedded via PipeCompose is degraded to text and
        never delivered to PipeImgGen.

        Observables:
        - The composed prompt text still mentions the image as a bare URL string (so the
          information visibly survived as text, not as an attachment).
        - `input_images` — the images actually sent to the model — is empty.
        """
        load_empty_library()
        composed_prompt_text, img_gen_prompt = await _compose_then_build_img_gen_prompt(job_metadata)

        # The image collapsed into the prompt text as a URL string instead of an attachment.
        assert "secret-token-glyph-7q2x" in composed_prompt_text

        # No image reaches the model, even though `source_image` was in working memory the
        # whole time — nothing on the PipeImgGen side referenced it.
        assert not img_gen_prompt.input_images

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: an image embedded in a PipeCompose template is flattened to a URL string "
        "and is not delivered to the downstream PipeImgGen. A fix should carry the image "
        "through the composed prompt so the generator receives it.",
    )
    async def test_image_embedded_in_compose_should_reach_img_gen(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
    ) -> None:
        """DESIRED behavior: the image embedded via PipeCompose should be delivered to the
        image model, i.e. it should appear in `input_images`.
        """
        load_empty_library()
        _composed_prompt_text, img_gen_prompt = await _compose_then_build_img_gen_prompt(job_metadata)

        assert img_gen_prompt.input_images is not None
        assert len(img_gen_prompt.input_images) == 1
