from typing import Any, Dict, List, Optional, Type, cast

from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import (
    ImggAssignment,
    Jinja2Assignment,
    LLMAssignment,
    LLMAssignmentFactory,
    ObjectAssignment,
    OcrAssignment,
    TextThenObjectAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.content_generation.imgg_generate import imgg_gen_image_list, imgg_gen_single_image
from pipelex.cogt.content_generation.jinja2_generate import jinja2_gen_text
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list, llm_gen_text
from pipelex.cogt.content_generation.ocr_generate import ocr_gen_extract_pages
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams
from pipelex.cogt.imgg.imgg_prompt import ImggPrompt
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_environment import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ContentGenerator(ContentGeneratorProtocol):
    @override
    @update_job_metadata
    async def make_llm_text(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        wfid: Optional[str] = None,
    ) -> str:
        log.verbose(f"{self.__class__.__name__} make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        llm_assignment = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        generated_text = await llm_gen_text(llm_assignment=llm_assignment)
        log.verbose(f"{self.__class__.__name__} generated text: {generated_text}")
        return generated_text

    @override
    @update_job_metadata
    async def make_object_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
        wfid: Optional[str] = None,
    ) -> BaseModelTypeVar:
        log.verbose(f"{self.__class__.__name__} make_object_direct: {llm_prompt_for_object}")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        obj = await llm_gen_object(object_assignment=object_assignment)
        log.verbose(f"{self.__class__.__name__} generated object direct: {obj}")
        return cast(BaseModelTypeVar, obj)

    @override
    @update_job_metadata
    async def make_text_then_object(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: Optional[LLMPromptFactoryAbstract] = None,
        wfid: Optional[str] = None,
    ) -> BaseModelTypeVar:
        llm_assignment_for_text = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )

        llm_assignment_factory_to_object = LLMAssignmentFactory(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt_factory=llm_prompt_factory_for_object or LLMPromptTemplate.for_structure_from_preliminary_text(),
        )
        workflow_arg = TextThenObjectAssignment(
            object_class_name=object_class.__name__,
            llm_assignment_for_text=llm_assignment_for_text,
            llm_assignment_factory_to_object=llm_assignment_factory_to_object,
        )

        preliminary_text = await llm_gen_text(llm_assignment=llm_assignment_for_text)

        log.dev(f"preliminary_text: {preliminary_text}")

        fup_llm_assignment = await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(
            preliminary_text=preliminary_text,
        )

        fup_obj_assignment = ObjectAssignment(
            llm_assignment_for_object=fup_llm_assignment,
            object_class_name=object_class.__name__,
        )

        obj = await llm_gen_object(object_assignment=fup_obj_assignment)
        log.verbose(f"{self.__class__.__name__} generated object after text: {obj}")
        return cast(BaseModelTypeVar, obj)

    @override
    @update_job_metadata
    async def make_object_list_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        wfid: Optional[str] = None,
    ) -> List[BaseModelTypeVar]:
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        obj_list = await llm_gen_object_list(object_assignment=object_assignment)
        log.verbose(f"{self.__class__.__name__} generated object list direct: {obj_list}")
        return cast(List[BaseModelTypeVar], obj_list)

    @override
    @update_job_metadata
    async def make_text_then_object_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: Optional[LLMPromptFactoryAbstract] = None,
        wfid: Optional[str] = None,
    ) -> List[BaseModelTypeVar]:
        llm_assignment_for_text = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )

        llm_assignment_factory_to_object = LLMAssignmentFactory(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt_factory=llm_prompt_factory_for_object_list or LLMPromptTemplate.for_structure_from_preliminary_text(),
        )
        workflow_arg = TextThenObjectAssignment(
            object_class_name=object_class.__name__,
            llm_assignment_for_text=llm_assignment_for_text,
            llm_assignment_factory_to_object=llm_assignment_factory_to_object,
        )

        preliminary_text = await llm_gen_text(llm_assignment=llm_assignment_for_text)

        log.dev(f"preliminary_text: {preliminary_text}")

        fup_llm_assignment = await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(
            preliminary_text=preliminary_text,
        )

        fup_obj_assignment = ObjectAssignment(
            llm_assignment_for_object=fup_llm_assignment,
            object_class_name=object_class.__name__,
        )

        obj_list = await llm_gen_object_list(object_assignment=fup_obj_assignment)
        log.verbose(f"{self.__class__.__name__} generated object list after text: {obj_list}")
        return cast(List[BaseModelTypeVar], obj_list)

    @override
    @update_job_metadata
    async def make_single_image(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
        wfid: Optional[str] = None,
    ) -> GeneratedImage:
        imgg_config = get_config().cogt.imgg_config
        imgg_assignment = ImggAssignment(
            job_metadata=job_metadata,
            imgg_handle=imgg_handle,
            imgg_prompt=imgg_prompt,
            imgg_job_params=imgg_job_params or imgg_config.make_default_imgg_job_params(),
            imgg_job_config=imgg_job_config or imgg_config.imgg_job_config,
            nb_images=1,
        )
        generated_image = await imgg_gen_single_image(imgg_assignment=imgg_assignment)
        log.dev(f"{self.__class__.__name__} generated image: {generated_image}")
        return generated_image

    @override
    @update_job_metadata
    async def make_image_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        nb_images: int,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
        wfid: Optional[str] = None,
    ) -> List[GeneratedImage]:
        imgg_config = get_config().cogt.imgg_config
        imgg_assignment = ImggAssignment(
            job_metadata=job_metadata,
            imgg_handle=imgg_handle,
            imgg_prompt=imgg_prompt,
            imgg_job_params=imgg_job_params or imgg_config.make_default_imgg_job_params(),
            imgg_job_config=imgg_job_config or imgg_config.imgg_job_config,
            nb_images=nb_images,
        )
        generated_image_list = await imgg_gen_image_list(imgg_assignment=imgg_assignment)
        log.dev(f"{self.__class__.__name__} generated image list: {generated_image_list}")
        return generated_image_list

    @override
    async def make_jinja2_text(
        self,
        context: Dict[str, Any],
        jinja2_name: Optional[str] = None,
        jinja2: Optional[str] = None,
        prompting_style: Optional[PromptingStyle] = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
        wfid: Optional[str] = None,
    ) -> str:
        jinja2_assignment = Jinja2Assignment(
            context=context,
            jinja2_name=jinja2_name,
            jinja2=jinja2,
            prompting_style=prompting_style,
            template_category=template_category,
        )
        jinja2_text = await jinja2_gen_text(jinja2_assignment=jinja2_assignment)
        log.dev(f"{self.__class__.__name__} jinja2: {jinja2_text}")
        return jinja2_text

    @override
    async def make_ocr_extract_pages(
        self,
        job_metadata: JobMetadata,
        ocr_input: OcrInput,
        ocr_handle: OcrHandle,
        ocr_job_params: Optional[OcrJobParams] = None,
        ocr_job_config: Optional[OcrJobConfig] = None,
        wfid: Optional[str] = None,
    ) -> OcrOutput:
        ocr_assignment = OcrAssignment(
            job_metadata=job_metadata,
            ocr_input=ocr_input,
            ocr_handle=ocr_handle,
            ocr_job_params=ocr_job_params or OcrJobParams.make_default_ocr_job_params(),
            ocr_job_config=ocr_job_config or OcrJobConfig(),
        )
        ocr_output = await ocr_gen_extract_pages(ocr_assignment=ocr_assignment)
        return ocr_output
