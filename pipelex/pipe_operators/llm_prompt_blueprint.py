from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex import log
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.core.stuffs.stuff_content import ImageContent, StuffContent
from pipelex.exceptions import (
    PipeDefinitionError,
    PipeInputError,
    PipeRunParamsError,
    WorkingMemoryVariableError,
)
from pipelex.hub import get_class_registry, get_content_generator, get_required_concept, get_template
from pipelex.tools.templating.jinja2_blueprint import Jinja2Blueprint
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.type_inspector import get_type_structure
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list, has_more_than_one_among_attributes_from_list


class LLMPromptBlueprint(BaseModel):
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
            raise PipeDefinitionError(
                f"PipeLLMPrompt user text must have exactly one of user_text, user_text_jinja2_blueprint or user_prompt_verbatim_name: {self}"
            )
        if has_more_than_one_among_attributes_from_list(
            obj=self,
            attributes_list=[
                "system_prompt_jinja2_blueprint",
                "system_prompt_verbatim_name",
                "system_prompt",
            ],
        ):
            raise PipeDefinitionError(
                f"PipeLLMPrompt system got more than one of system_prompt, system_prompt_jinja2_blueprint, system_prompt_verbatim_name: {self}"
            )
        return self

    def validate_with_libraries(self):
        if self.user_prompt_verbatim_name:
            get_template(template_name=self.user_prompt_verbatim_name)
        if self.system_prompt_verbatim_name:
            get_template(template_name=self.system_prompt_verbatim_name)

        if self.user_text_jinja2_blueprint:
            self.user_text_jinja2_blueprint.validate_with_libraries()
        if self.system_prompt_jinja2_blueprint:
            self.system_prompt_jinja2_blueprint.validate_with_libraries()

    def required_variables(self) -> Set[str]:
        required_variables: Set[str] = set()
        if self.user_text_jinja2_blueprint:
            required_variables.update(self.user_text_jinja2_blueprint.required_variables())
        if self.system_prompt_jinja2_blueprint:
            required_variables.update(self.system_prompt_jinja2_blueprint.required_variables())
        if self.user_images:
            user_images_top_object_name = [user_image.split(".", 1)[0] for user_image in self.user_images]
            required_variables.update(user_images_top_object_name)
        return required_variables

    async def make_llm_prompt(
        self,
        output_concept_string: str,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
    ) -> LLMPrompt:
        if pipe_run_params.is_multiple_output_required:
            raise PipeRunParamsError(
                f"PipeLLMPrompt does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            )

        ############################################################
        # User images
        ############################################################
        prompt_user_images: List[PromptImage] = []
        if self.user_images:
            for user_image_name in self.user_images:
                log.debug(f"Getting user image '{user_image_name}' from context")
                try:
                    prompt_image_content = working_memory.get_stuff_or_attribute(name=user_image_name, wanted_type=ImageContent)
                except WorkingMemoryVariableError as exc:
                    raise PipeInputError(f"Could not find a valid user image named '{user_image_name}' in the working_memory: {exc}") from exc

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
            working_memory=working_memory,
            jinja2_blueprint=self.user_text_jinja2_blueprint,
            text_verbatim_name=self.user_prompt_verbatim_name,
            fixed_text=self.user_text,
            pipe_run_params=pipe_run_params,
        )
        if not user_text:
            raise ValueError("For user_text we need either a pipe_jinja2, a text_verbatim_name or a fixed user_text")

        # Append output structure prompt if needed
        if pipe_run_params.dynamic_output_concept_code:
            user_text += LLMPromptBlueprint.get_output_structure_prompt(
                concept_string=pipe_run_params.dynamic_output_concept_code,
                is_with_preliminary_text=pipe_run_params.is_with_preliminary_text or False,
            )
        else:
            user_text += LLMPromptBlueprint.get_output_structure_prompt(
                concept_string=output_concept_string,
                is_with_preliminary_text=pipe_run_params.is_with_preliminary_text or False,
            )

        log.verbose(f"User text with {output_concept_string=}:\n {user_text}")

        ############################################################
        # System text
        ############################################################
        system_text = await self._unravel_text(
            working_memory=working_memory,
            jinja2_blueprint=self.system_prompt_jinja2_blueprint,
            text_verbatim_name=self.system_prompt_verbatim_name,
            fixed_text=self.system_prompt,
            pipe_run_params=pipe_run_params,
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

    @staticmethod
    def get_output_structure_prompt(concept_string: str, is_with_preliminary_text: bool) -> str:
        concept = get_required_concept(concept_string=concept_string)
        class_name = concept.structure_class_name
        output_class = get_class_registry().get_class(class_name)
        if not output_class:
            return ""

        class_structure = get_type_structure(output_class, base_class=StuffContent)

        if not class_structure:
            return ""

        class_structure_str = "\n".join(class_structure)

        # TODO: use proper prompt templating for this
        if is_with_preliminary_text:
            output_structure_prompt = (
                f"\n\n---\nRequested output format: The requested output will be used to define the following class: {class_name}\n"
                f"{class_structure_str}\n"
                "You do NOT need to output a formatted JSON object, another LLM will take care of that. "
                "If you cannot find a value that is Optional, output None for that field. "
                "However, you MUST clearly output the values for each of these fields in your response.\n---\n"
                "DO NOT create information. If the information is not present, output None."
            )
        else:
            output_structure_prompt = (
                f"\n\n---\nRequested output format: The output must conform to the following BaseModel: {class_name}\n"
                f"{class_structure_str}\n"
                "If you cannot find a value that is Optional, output None for that field. "
                "However, you MUST clearly output the values for each of these fields in your response.\n---\n"
                "DO NOT create information. If the information is not present, output None."
            )
        return output_structure_prompt

    async def _unravel_text(
        self,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        jinja2_blueprint: Optional[Jinja2Blueprint],
        text_verbatim_name: Optional[str],
        fixed_text: Optional[str],
    ) -> Optional[str]:
        the_text: Optional[str]
        if jinja2_blueprint:
            log.verbose(f"Working with Jinja2 pipe '{jinja2_blueprint.jinja2_name}'")
            if pipe_run_params.is_multiple_output_required:
                raise PipeRunParamsError(
                    f"PipeJinja2 does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
                )
            if (prompting_style := self.prompting_style) and not jinja2_blueprint.prompting_style:
                jinja2_blueprint.prompting_style = prompting_style
                log.verbose(f"Setting prompting style to {prompting_style}")

            context: Dict[str, Any] = working_memory.generate_stuff_artefact_dict()
            if pipe_run_params:
                context.update(**pipe_run_params.params)
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
