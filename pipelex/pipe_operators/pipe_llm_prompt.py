# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import ClassVar, List, Optional, Self, Set

from kajson.class_registry import class_registry
from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.config import get_config
from pipelex.core.concept import Concept
from pipelex.core.concept_native import NativeConceptCode
from pipelex.core.domain import SpecialDomain
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ImageContent, LLMPromptContent, StuffContent, StuffContentError
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError, PipeRunParamsError
from pipelex.hub import get_template
from pipelex.job_metadata import JobCategory, JobMetadata
from pipelex.pipe_operators.pipe_jinja2 import PipeJinja2
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.utils.class_structure_utils import get_type_structure
from pipelex.tools.utils.path_utils import clarify_path_or_url
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list, has_more_than_one_among_attributes_from_list


class PipeLLMPromptOutput(PipeOutput):
    @property
    def llm_prompt(self) -> LLMPrompt:
        return self.main_stuff_as(content_type=LLMPromptContent)


# TODO: consider adding a PipeLLMPromptFactory for consistency
class PipeLLMPrompt(PipeAbstract):
    adhoc_pipe_code: ClassVar[str] = "adhoc_pipe_code_for_prompt_llm"

    output_concept_code: str = f"{SpecialDomain.NATIVE}.{NativeConceptCode.LLM_PROMPT}"

    prompting_style: Optional[PromptingStyle] = None

    system_prompt_pipe_jinja2: Optional[PipeJinja2] = None
    system_prompt_verbatim_name: Optional[str] = None
    system_prompt: Optional[str] = None

    user_pipe_jinja2: Optional[PipeJinja2] = None
    user_prompt_verbatim_name: Optional[str] = None
    user_text: Optional[str] = None

    user_images: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_user_text(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(
            obj=self,
            attributes_list=[
                "user_text",
                "user_pipe_jinja2",
                "user_prompt_verbatim_name",
            ],
        ):
            raise PipeDefinitionError(
                f"PipeLLMPrompt user text must have exactly one of user_text, user_pipe_jinja2 or user_prompt_verbatim_name: {self}"
            )
        if has_more_than_one_among_attributes_from_list(
            obj=self,
            attributes_list=[
                "system_prompt",
                "system_prompt_pipe_jinja2",
                "system_prompt_verbatim_name",
            ],
        ):
            raise PipeDefinitionError(
                f"PipeLLMPrompt system got more than one of system_prompt, system_prompt_pipe_jinja2, system_prompt_verbatim_name: {self}"
            )
        return self

    @override
    def validate_with_libraries(self):
        if self.user_prompt_verbatim_name:
            get_template(template_name=self.user_prompt_verbatim_name)
        if self.system_prompt_verbatim_name:
            get_template(template_name=self.system_prompt_verbatim_name)

        if self.user_pipe_jinja2:
            self.user_pipe_jinja2.validate_with_libraries()
        if self.system_prompt_pipe_jinja2:
            self.system_prompt_pipe_jinja2.validate_with_libraries()

    @override
    def required_variables(self) -> Set[str]:
        required_variables: Set[str] = set()
        if self.user_pipe_jinja2:
            required_variables.update(self.user_pipe_jinja2.required_variables())
        if self.system_prompt_pipe_jinja2:
            required_variables.update(self.system_prompt_pipe_jinja2.required_variables())
        if self.user_images:
            required_variables.update(self.user_images)
        return required_variables

    @override
    @update_job_metadata_for_pipe
    async def run_pipe(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        pipe_code: str,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeLLMPromptOutput:
        if pipe_run_params.is_multiple_output_required:
            raise PipeRunParamsError(
                f"PipeLLMPrompt does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            )
        if not self.output_concept_code:
            raise PipeRunParamsError("PipeLLMPrompt must have a fixed non-None output_concept_code")

        ############################################################
        # User images
        ############################################################
        user_images: List[PromptImage] = []
        if self.user_images:
            for user_image_name in self.user_images:
                log.debug(f"Getting user image '{user_image_name}' from context")
                user_image_stuff = working_memory.get_stuff(user_image_name)
                if not user_image_stuff:
                    raise StuffContentError(f"User image '{user_image_name}' not found in context")
                prompt_image_stuff_content = user_image_stuff.content
                if not isinstance(prompt_image_stuff_content, ImageContent):
                    raise ValueError(f"Expected ImageContent, got {user_image_stuff.content.__class__}")
                image_url = prompt_image_stuff_content.url
                file_path, url = clarify_path_or_url(path_or_url=image_url)
                user_image = PromptImageFactory.make_prompt_image(
                    file_path=file_path,
                    url=url,
                )
                user_images.append(user_image)

        ############################################################
        # User text
        ############################################################
        user_text = await self._unravel_text(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_jinja2=self.user_pipe_jinja2,
            text_verbatim_name=self.user_prompt_verbatim_name,
            fixed_text=self.user_text,
            pipe_run_params=pipe_run_params,
        )
        if not user_text:
            raise ValueError("For user_text we need either a pipe_jinja2, a text_verbatim_name or a fixed user_text")

        # Append output structure prompt if needed
        if pipe_run_params.output_concept_code:
            user_text += PipeLLMPrompt.get_output_structure_prompt(output_concept=pipe_run_params.output_concept_code)

        ############################################################
        # System text
        ############################################################
        system_text = await self._unravel_text(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_jinja2=self.system_prompt_pipe_jinja2,
            text_verbatim_name=self.system_prompt_verbatim_name,
            fixed_text=self.system_prompt,
            pipe_run_params=pipe_run_params,
        )

        ############################################################
        # Full LLMPrompt
        ############################################################
        llm_prompt = LLMPromptContent(
            system_text=system_text,
            user_text=user_text,
            user_images=user_images,
        )

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept_code=self.output_concept_code,
            content=llm_prompt,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeLLMPromptOutput(
            working_memory=working_memory,
        )
        return pipe_output

    @staticmethod
    def get_output_structure_prompt(output_concept: str) -> str:
        class_name = Concept.extract_concept_name_from_str(concept_str=output_concept)
        output_class = class_registry.get_class(class_name)
        if not output_class:
            return ""

        fields = get_type_structure(output_class, base_class=StuffContent)

        if not fields:
            return ""

        output_structure_prompt = (
            f"\n\n---\nRequested output format: The output should contain the following fields:\n"
            f"{chr(10).join(fields)}\n"
            "You do NOT need to output a formatted JSON object, another LLM will take care of that. "
            "However, you MUST clearly output the values for each of these fields in your response.\n---\n"
        )
        return output_structure_prompt

    async def _unravel_text(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        pipe_jinja2: Optional[PipeJinja2],
        text_verbatim_name: Optional[str],
        fixed_text: Optional[str],
    ) -> Optional[str]:
        the_text: Optional[str]
        if pipe_jinja2:
            log.verbose(f"Working with Jinja2 pipe '{pipe_jinja2.jinja2_name}'")
            if (prompting_style := self.prompting_style) and not pipe_jinja2.prompting_style:
                pipe_jinja2.prompting_style = prompting_style
                log.verbose(f"Setting prompting style to {prompting_style}")

            jinja2_job_metadata = job_metadata.copy_with_update(
                updated_metadata=JobMetadata(
                    session_id=get_config().session_id,
                    job_category=JobCategory.JINJA2_JOB,
                )
            )
            the_text = (
                await pipe_jinja2.run_pipe(
                    pipe_code=PipeJinja2.adhoc_pipe_code,
                    job_metadata=jinja2_job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                )
            ).rendered_text
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
