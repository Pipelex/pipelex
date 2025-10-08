from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, model_validator

from pipelex import log
from pipelex.cogt.exceptions import LLMPromptSpecError
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_content_generator
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract, ContextProviderException
from pipelex.tools.templating.jinja2_blueprint import Jinja2Blueprint
from pipelex.tools.templating.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.templating.template_preprocessor import preprocess_template
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list, has_more_than_one_among_attributes_from_list
from pipelex.types import Self

if TYPE_CHECKING:
    from pipelex.cogt.image.prompt_image import PromptImage


# TODO: move this to pipe operators
class LLMPromptSpec(BaseModel):
    prompting_style: PromptingStyle | None = None
    system_prompt_jinja2_blueprint: Jinja2Blueprint | None = None
    user_text_jinja2_blueprint: Jinja2Blueprint | None = None
    user_images: list[str] | None = None

    def validate_with_libraries(self):
        pass

    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()
        if self.user_images:
            user_images_top_object_name = [user_image.split(".", 1)[0] for user_image in self.user_images]
            required_variables.update(user_images_top_object_name)

        if self.user_text_jinja2_blueprint:
            template_source = preprocess_template(self.user_text_jinja2_blueprint.jinja2)
            required_variables.update(
                detect_jinja2_required_variables(
                    template_category=self.user_text_jinja2_blueprint.template_category,
                    template_source=template_source,
                )
            )

        if self.system_prompt_jinja2_blueprint:
            system_prompt_template_source = preprocess_template(self.system_prompt_jinja2_blueprint.jinja2)
            required_variables.update(
                detect_jinja2_required_variables(
                    template_category=self.system_prompt_jinja2_blueprint.template_category,
                    template_source=system_prompt_template_source,
                )
            )

        return {
            variable_name
            for variable_name in required_variables
            if not variable_name.startswith("_") and variable_name not in ("preliminary_text", "place_holder")
        }

    # TODO: make this consistent with `LLMPromptFactoryAbstract` or `LLMPromptTemplate`,
    # let's get back to it when we have a better solution for structuring_method
    async def make_llm_prompt(
        self,
        output_concept_string: str,
        context_provider: ContextProviderAbstract,
        output_structure_prompt: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> LLMPrompt:
        ############################################################
        # User images
        ############################################################
        prompt_user_images: dict[str, PromptImage] = {}
        if self.user_images:
            for user_image_name in self.user_images:
                log.debug(f"Getting user image '{user_image_name}' from context")
                # Try to get as a single ImageContent first
                try:
                    prompt_image_content = context_provider.get_typed_object_or_attribute(name=user_image_name, wanted_type=ImageContent)
                    if prompt_image_content is not None:  # An ImageContent can be optional
                        if base_64 := prompt_image_content.base_64:
                            user_image = PromptImageFactory.make_prompt_image(base_64=base_64)
                        else:
                            image_uri = prompt_image_content.url
                            user_image = PromptImageFactory.make_prompt_image_from_uri(uri=image_uri)
                        prompt_user_images[user_image_name] = user_image
                except ContextProviderException:
                    # If single image failed, try to get as a collection (list or tuple)
                    try:
                        image_collection = context_provider.get_typed_object_or_attribute(name=user_image_name, wanted_type=None)
                        # Check if it's a list or tuple
                        if isinstance(image_collection, (list, tuple)):
                            for image_item in image_collection:  # type: ignore[assignment]
                                if isinstance(image_item, ImageContent):
                                    item_base_64 = image_item.base_64
                                    if item_base_64:
                                        user_image = PromptImageFactory.make_prompt_image(base_64=item_base_64)  # type: ignore[arg-type]
                                    else:
                                        image_uri = image_item.url
                                        user_image = PromptImageFactory.make_prompt_image_from_uri(uri=image_uri)
                                    prompt_user_images[user_image_name] = user_image
                        else:
                            msg = (
                                f"Could not find a valid user image or image collection named '{user_image_name}' from the provided context_provider"
                            )
                            raise LLMPromptSpecError(msg)
                    except ContextProviderException as exc:
                        msg = f"Could not find a valid user image named '{user_image_name}' from the provided context_provider: {exc}"
                        raise LLMPromptSpecError(msg) from exc

        ############################################################
        # User text
        ############################################################
        # replace the image variables with numbered tags
        if prompt_user_images:
            if not extra_params:
                extra_params = {}
            for image_index, image_name in enumerate(prompt_user_images.keys()):
                extra_params[image_name] = f"[Image {image_index + 1}]"
                log.warning(f"Replacing image variable '{image_name}' with numbered tag '[Image {image_index + 1}]'")
        user_text: str | None = None
        if self.user_text_jinja2_blueprint:
            user_text = await self._unravel_text(
                context_provider=context_provider,
                jinja2_blueprint=self.user_text_jinja2_blueprint,
                extra_params=extra_params,
            )
            if output_structure_prompt:
                user_text += output_structure_prompt
        else:
            user_text = output_structure_prompt
            # Note that output_structure_prompt can be None
            # it's OK to have a null user_text

        log.verbose(f"User text with {output_concept_string=}:\n {user_text}")

        ############################################################
        # System text
        ############################################################
        system_text: str | None = None
        if self.system_prompt_jinja2_blueprint:
            system_text = await self._unravel_text(
                context_provider=context_provider,
                jinja2_blueprint=self.system_prompt_jinja2_blueprint,
                extra_params=extra_params,
            )

        ############################################################
        # Full LLMPrompt
        ############################################################
        return LLMPrompt(
            system_text=system_text,
            user_text=user_text,
            user_images=list(prompt_user_images.values()),
        )

    async def _unravel_text(
        self,
        context_provider: ContextProviderAbstract,
        jinja2_blueprint: Jinja2Blueprint,
        extra_params: dict[str, Any] | None = None,
    ) -> str:
        if (prompting_style := self.prompting_style) and not jinja2_blueprint.prompting_style:
            jinja2_blueprint.prompting_style = prompting_style
            log.verbose(f"Setting prompting style to {prompting_style}")

        log.info(f"extra_params: {extra_params}")
        log.info(f"jinja2_blueprint.extra_context: {jinja2_blueprint.extra_context}")

        context: dict[str, Any] = context_provider.generate_jinja2_context()
        if extra_params:
            context.update(**extra_params)
        if jinja2_blueprint.extra_context:
            context.update(**jinja2_blueprint.extra_context)

        return await get_content_generator().make_jinja2_text(
            context=context,
            jinja2=jinja2_blueprint.jinja2,
            prompting_style=self.prompting_style,
            template_category=jinja2_blueprint.template_category,
        )
