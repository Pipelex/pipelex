"""Blueprint for image-generation prompts: the authored shape, and its input contract.

Parse-and-validate lives here; the *assembly* — image registry, `[Image N]` placeholders, template
rendering — moved to `pipelex.kernel.img_gen_prompt`, so a caller with no interpreter can build an
`ImgGenPrompt` too. This class keeps what is genuinely blueprint-shaped: the authored fields, the
declared input variables, and the `max_prompt_images` limit, whose breach is an interpreter-layer
error about the model the pipe chose.
"""

from typing import Any

from pydantic import BaseModel

from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.kernel.img_gen_prompt import assemble_img_gen_prompt
from pipelex.kernel.prompt_references import ImageReference
from pipelex.pipe_operators.img_gen.exceptions import PipeImgGenFactoryError
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.tools.templating.templating_style import TemplatingStyle


class ImgGenPromptBlueprint(BaseModel):
    """The authored shape of an image-generation prompt, and its input contract.

    This class no longer assembles anything. Template rendering, image-reference extraction,
    `[Image N]` placeholder generation and `input_images` collection all live in
    `pipelex.kernel.img_gen_prompt.assemble_img_gen_prompt`, so a caller with no interpreter can
    build an `ImgGenPrompt` too. What stays here is what is genuinely blueprint-shaped:

    - the authored fields (`prompt_blueprint`, `negative_prompt_blueprint`, `image_references`)
    - the input variables they declare (`required_variables`)
    - the `max_prompt_images` limit, whose breach is an interpreter-layer error about the model
      the pipe chose, and which is therefore applied here rather than in the kernel

    Add assembly behavior to the kernel module, not to this class.
    """

    prompt_blueprint: TemplateBlueprint | None = None
    negative_prompt_blueprint: TemplateBlueprint | None = None
    image_references: list[ImageReference] | None = None

    def required_variables(self) -> set[str]:
        """Return the set of required variables from templates and image references."""
        required_variables: set[str] = set()

        if self.image_references:
            image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.image_references]
            required_variables.update(image_ref_root_names)

        if self.prompt_blueprint:
            required_variables.update(get_root_from_dotted_path(path) for path in self.prompt_blueprint.required_variables())
        if self.negative_prompt_blueprint:
            required_variables.update(get_root_from_dotted_path(path) for path in self.negative_prompt_blueprint.required_variables())

        return {variable_name for variable_name in required_variables if not variable_name.startswith("_")}

    async def make_img_gen_prompt(
        self,
        *,
        context_provider: ContextProviderAbstract,
        templating_style: TemplatingStyle,
        extra_params: dict[str, Any] | None = None,
        max_prompt_images: int | None = None,
    ) -> ImgGenPrompt:
        """Build an `ImgGenPrompt` from the blueprint, delegating the assembly to the kernel.

        Raises `PromptContentError` (from the kernel) if an image reference cannot be resolved, and
        `PipeImgGenFactoryError` if more images were collected than the chosen model accepts.
        """
        img_gen_prompt = await assemble_img_gen_prompt(
            context_provider=context_provider,
            templating_style=templating_style,
            prompt_blueprint=self.prompt_blueprint,
            negative_prompt_blueprint=self.negative_prompt_blueprint,
            image_references=self.image_references,
            extra_params=extra_params,
        )

        # Enforced here rather than in the kernel: the limit is a property of the model this pipe
        # chose, and its breach raises an interpreter-layer error.
        input_images = img_gen_prompt.input_images
        if max_prompt_images is not None and input_images is not None and len(input_images) > max_prompt_images:
            msg = (
                f"Too many input images: got {len(input_images)}, but model only supports {max_prompt_images}. "
                f"Reduce the number of images in your template."
            )
            raise PipeImgGenFactoryError(msg)

        return img_gen_prompt
