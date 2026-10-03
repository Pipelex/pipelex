"""An image's established format rides into the prompt, the way a document's already does.

Run setup stamps every image input with the `mime_type` of its bytes. Assembling the prompt used to
build each prompt image from its url alone and drop that stamp, so the LLM worker had to guess the
format again, from a provider-side sniff, and could not refuse a non-image before the provider did.
"""

import pytest

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.kernel.llm_prompt_content import LlmPromptContent, assemble_llm_prompt
from pipelex.kernel.prompt_references import ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

STORED_IMAGE_URI = "pipelex-storage://org/uploads/photo.png"


class TestLlmPromptImageMimeType:
    def test_the_factory_keeps_a_given_mime_type(self):
        prompt_image = PromptImageFactory.make_prompt_image(uri=STORED_IMAGE_URI, mime_type="image/png")

        assert isinstance(prompt_image, PromptImageUri)
        assert prompt_image.mime_type == "image/png"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_assembled_prompt_image_carries_the_content_mime_type(self):
        memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
                content=ImageContent(url=STORED_IMAGE_URI, mime_type="application/pdf"),
                name="photo",
            ),
        )
        prompt_content = LlmPromptContent(
            user_template=TemplateBlueprint(template="Describe the photo.", category=TemplateCategory.LLM_PROMPT),
            user_image_references=[ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT)],
        )

        llm_prompt = await assemble_llm_prompt(
            prompt_content=prompt_content,
            context_provider=memory,
            templating_style=TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN),
        )

        assert len(llm_prompt.user_images) == 1
        prompt_image = llm_prompt.user_images[0]
        assert isinstance(prompt_image, PromptImageUri)
        assert prompt_image.uri == STORED_IMAGE_URI
        assert prompt_image.mime_type == "application/pdf"
