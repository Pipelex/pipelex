from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex import log
from pipelex.cogt.exceptions import LLMPromptSpecError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.core.stuffs.stuff_content import ImageContent
from pipelex.hub import get_content_generator, get_template, get_template_provider
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract, ContextProviderException
from pipelex.tools.templating.jinja2_blueprint import Jinja2Blueprint
from pipelex.tools.templating.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list, has_more_than_one_among_attributes_from_list


class LLMPromptSpec(BaseModel):
    prompting_style: Optional[PromptingStyle] = None

    system_prompt_jinja2_blueprint: Optional[Jinja2Blueprint] = None
    system_prompt_verbatim_name: Optional[str] = None
    system_prompt: Optional[str] = None

    user_text_jinja2_blueprint: Optional[Jinja2Blueprint] = None
    user_prompt_verbatim_name: Optional[str] = None
    user_text: Optional[str] = None

    user_images: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_user_text(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(
            obj=self,
            attributes_list=[
                "user_text_jinja2_blueprint",
                "user_prompt_verbatim_name",
                "user_text",
            ],
        ):
            raise LLMPromptSpecError(
                f"LLMPromptSpec user text must have exactly one of user_text, user_text_jinja2_blueprint or user_prompt_verbatim_name: {self}"
            )
        if has_more_than_one_among_attributes_from_list(
            obj=self,
            attributes_list=[
                "system_prompt_jinja2_blueprint",
                "system_prompt_verbatim_name",
                "system_prompt",
            ],
        ):
            raise LLMPromptSpecError(
                f"LLMPromptSpec system got more than one of system_prompt, system_prompt_jinja2_blueprint, system_prompt_verbatim_name: {self}"
            )
        return self

    def validate_with_libraries(self):
        if self.user_prompt_verbatim_name:
            get_template(template_name=self.user_prompt_verbatim_name)
        if self.system_prompt_verbatim_name:
            get_template(template_name=self.system_prompt_verbatim_name)

        if self.user_text_jinja2_blueprint and self.user_text_jinja2_blueprint.jinja2_name:
            the_template = get_template(template_name=self.user_text_jinja2_blueprint.jinja2_name)
            log.debug(f"Validated jinja2 template '{self.user_text_jinja2_blueprint.jinja2_name}':\n{the_template}")
        if self.system_prompt_jinja2_blueprint and self.system_prompt_jinja2_blueprint.jinja2_name:
            the_template = get_template(template_name=self.system_prompt_jinja2_blueprint.jinja2_name)
            log.debug(f"Validated jinja2 template '{self.system_prompt_jinja2_blueprint.jinja2_name}':\n{the_template}")

    def required_variables(self) -> Set[str]:
        required_variables: Set[str] = set()
        if self.user_images:
            user_images_top_object_name = [user_image.split(".", 1)[0] for user_image in self.user_images]
            required_variables.update(user_images_top_object_name)

        if self.user_text_jinja2_blueprint:
            required_variables = detect_jinja2_required_variables(
                template_category=self.user_text_jinja2_blueprint.template_category,
                template_provider=get_template_provider(),
                jinja2_name=self.user_text_jinja2_blueprint.jinja2_name,
                jinja2=self.user_text_jinja2_blueprint.jinja2,
            )
        return {
            variable_name
            for variable_name in required_variables
            if not variable_name.startswith("_") and variable_name != "preliminary_text" and variable_name != "place_holder"
        }

    # TODO: make this consistent with `LLMPromptFactoryAbstract` or `LLMPromptTemplate`,
    # let's get back to it when we have a better solution for structuring_method
    async def make_llm_prompt(
        self,
        output_concept_string: str,
        context_provider: ContextProviderAbstract,
        output_structure_prompt: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> LLMPrompt:
        ############################################################
        # User images
        ############################################################
        prompt_user_images: List[PromptImage] = []
        if self.user_images:
            for user_image_name in self.user_images:
                log.debug(f"Getting user image '{user_image_name}' from context")
                try:
                    prompt_image_content = context_provider.get_typed_object_or_attribute(name=user_image_name, wanted_type=ImageContent)
                except ContextProviderException as exc:
                    raise LLMPromptSpecError(
                        f"Could not find a valid user image named '{user_image_name}' from the provided context_provider: {exc}"
                    ) from exc

                if prompt_image_content is not None:  # An ImageContent can be optional..
                    if base_64 := prompt_image_content.base_64:
                        user_image = PromptImageFactory.make_prompt_image(base_64=base_64)
                    else:
                        image_uri = prompt_image_content.url
                        user_image = PromptImageFactory.make_prompt_image_from_uri(uri=image_uri)
                    prompt_user_images.append(user_image)

        ############################################################
        # User text
        ############################################################
        user_text = await self._unravel_text(
            context_provider=context_provider,
            jinja2_blueprint=self.user_text_jinja2_blueprint,
            text_verbatim_name=self.user_prompt_verbatim_name,
            fixed_text=self.user_text,
            extra_params=extra_params,
        )
        if not user_text:
            raise ValueError("For user_text we need either a pipe_jinja2, a text_verbatim_name or a fixed user_text")

        if output_structure_prompt:
            user_text += output_structure_prompt

        log.verbose(f"User text with {output_concept_string=}:\n {user_text}")

        ############################################################
        # System text
        ############################################################
        system_text = await self._unravel_text(
            context_provider=context_provider,
            jinja2_blueprint=self.system_prompt_jinja2_blueprint,
            text_verbatim_name=self.system_prompt_verbatim_name,
            fixed_text=self.system_prompt,
            extra_params=extra_params,
        )

        ############################################################
        # Full LLMPrompt
        ############################################################
        llm_prompt = LLMPrompt(
            system_text=system_text,
            user_text=user_text,
            user_images=prompt_user_images,
        )

        return llm_prompt

    async def _unravel_text(
        self,
        context_provider: ContextProviderAbstract,
        jinja2_blueprint: Optional[Jinja2Blueprint],
        text_verbatim_name: Optional[str],
        fixed_text: Optional[str],
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        the_text: Optional[str]
        if jinja2_blueprint:
            log.verbose(f"Working with Jinja2 pipe '{jinja2_blueprint.jinja2_name}'")
            if (prompting_style := self.prompting_style) and not jinja2_blueprint.prompting_style:
                jinja2_blueprint.prompting_style = prompting_style
                log.verbose(f"Setting prompting style to {prompting_style}")

            context: Dict[str, Any] = context_provider.generate_context()
            if extra_params:
                context.update(**extra_params)
            if jinja2_blueprint.extra_context:
                context.update(**jinja2_blueprint.extra_context)

            the_text = await get_content_generator().make_jinja2_text(
                context=context,
                jinja2_name=jinja2_blueprint.jinja2_name,
                jinja2=jinja2_blueprint.jinja2,
                prompting_style=self.prompting_style,
                template_category=jinja2_blueprint.template_category,
            )
        elif text_verbatim_name:
            user_text_verbatim = get_template(
                template_name=text_verbatim_name,
            )
            if not user_text_verbatim:
                raise ValueError(f"Could not find text_verbatim template '{text_verbatim_name}'")
            the_text = user_text_verbatim
        elif fixed_text:
            the_text = fixed_text
        else:
            the_text = None
        return the_text
