"""The kernel can build an `ImgGenPrompt`, and builds the same one the blueprint does.

`run_img_gen` takes a ready `ImgGenPrompt`, so before this constructor existed a `RuntimeBoot`-only
process could call every other operator op and not the image one — the sole builder was an
interpreter-layer blueprint. That made the package's "callable without the interpreter" guarantee
false for exactly one operator, and a guarantee at less than 100% is worth nothing.

The gate is equality, not merely "it runs": the blueprint now delegates here, so the two must agree
by construction — and the assertion is what will catch it if someone later reintroduces assembly on
the interpreter side. What is actually easy to get wrong, and what these cases pin, is the
correspondence between the `[Image N]` tokens in the text and the order of `input_images`: the
registry is the single source of truth for both, and a mismatch mislabels which image the prompt is
describing with nothing downstream able to notice.
"""

import pytest

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.kernel.exceptions import PromptContentError
from pipelex.kernel.img_gen_prompt import assemble_img_gen_prompt
from pipelex.kernel.prompt_references import ImageReference, ImageReferenceKind
from pipelex.pipe_operators.img_gen.img_gen_prompt_blueprint import ImgGenPromptBlueprint
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle

# Explicit rather than resolved: these are unit tests over the assembly itself, so the style they
# render under is stated here instead of read out of config.
_TEMPLATING_STYLE = TemplatingStyle(tag_style=TagStyle.XML)

IMAGE_URL_1 = "https://example.com/first.png"
IMAGE_URL_2 = "https://example.com/second.png"


def _memory_with_images() -> WorkingMemory:
    image_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE)
    return WorkingMemoryFactory.make_from_multiple_stuffs(
        [
            StuffFactory.make_stuff(concept=image_concept, content=ImageContent(url=IMAGE_URL_1), name="hero"),
            StuffFactory.make_stuff(concept=image_concept, content=ImageContent(url=IMAGE_URL_2), name="sidekick"),
        ]
    )


def _prompt_template() -> TemplateBlueprint:
    return TemplateBlueprint(template="Draw {{ hero }} next to {{ sidekick }}.", category=TemplateCategory.IMG_GEN_PROMPT)


def _image_references() -> list[ImageReference]:
    return [
        ImageReference(variable_path="hero", kind=ImageReferenceKind.DIRECT),
        ImageReference(variable_path="sidekick", kind=ImageReferenceKind.DIRECT),
    ]


class TestImgGenPromptKernel:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_tokens_are_numbered_from_the_registry_that_orders_input_images(self) -> None:
        prompt = await assemble_img_gen_prompt(
            templating_style=_TEMPLATING_STYLE,
            context_provider=_memory_with_images(),
            prompt_blueprint=_prompt_template(),
            image_references=_image_references(),
        )

        assert prompt.input_images is not None
        assert all(isinstance(image, PromptImageUri) for image in prompt.input_images)
        uris = [image.uri for image in prompt.input_images if isinstance(image, PromptImageUri)]
        assert uris == [IMAGE_URL_1, IMAGE_URL_2]
        assert "[Image 1]" in prompt.positive_text
        assert "[Image 2]" in prompt.positive_text
        assert prompt.positive_text.index("[Image 1]") < prompt.positive_text.index("[Image 2]"), (
            "token order must follow registry order, which is the order of `input_images` — if these "
            "diverge the prompt names the wrong image and nothing downstream can tell."
        )
        assert IMAGE_URL_1 not in prompt.positive_text, "a raw URL in the text means the placeholder substitution was skipped"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_kernel_and_the_blueprint_build_the_same_prompt(self) -> None:
        """Both readers, same answer — the property the blueprint's delegation has to preserve."""
        from_kernel = await assemble_img_gen_prompt(
            templating_style=_TEMPLATING_STYLE,
            context_provider=_memory_with_images(),
            prompt_blueprint=_prompt_template(),
            image_references=_image_references(),
        )
        from_blueprint = await ImgGenPromptBlueprint(
            prompt_blueprint=_prompt_template(),
            image_references=_image_references(),
        ).make_img_gen_prompt(context_provider=_memory_with_images(), templating_style=_TEMPLATING_STYLE)

        assert from_kernel == from_blueprint

    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_unresolvable_reference_raises_the_kernel_error(self) -> None:
        """The error moved into the kernel with the code that raises it, so it is the kernel's."""
        with pytest.raises(PromptContentError):
            await assemble_img_gen_prompt(
                templating_style=_TEMPLATING_STYLE,
                context_provider=_memory_with_images(),
                prompt_blueprint=TemplateBlueprint(template="Draw {{ nobody }}.", category=TemplateCategory.IMG_GEN_PROMPT),
                image_references=[ImageReference(variable_path="nobody", kind=ImageReferenceKind.DIRECT)],
            )
