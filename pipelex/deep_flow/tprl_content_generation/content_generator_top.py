from typing import Any, cast

from pydantic import BaseModel  # noqa: TC002
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    LLMAssignment,
    LLMAssignmentFactory,
    ObjectAssignment,
    TemplatingAssignment,
    TextThenObjectAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.config import get_config
from pipelex.deep_flow.exceptions import ContentGenerationError
from pipelex.deep_flow.tprl.conditional_worker import with_conditional_worker
from pipelex.deep_flow.tprl.workflow_caller import WorkflowExecutor
from pipelex.deep_flow.tprl_content_generation.content_generator_models import AssignmentType, ResultType
from pipelex.deep_flow.tprl_content_generation.wf_make_extract import WfMakeOcr
from pipelex.deep_flow.tprl_content_generation.wf_make_images import WfMakeImages
from pipelex.deep_flow.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from pipelex.deep_flow.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from pipelex.deep_flow.tprl_content_generation.wf_make_object import (
    WfMakeObject,
    WfMakeObjectList,
    WfMakeTextThenObject,
    WfMakeTextThenObjectList,
)
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.templating_models import PromptingTarget
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ContentGeneratorTop(WorkflowExecutor[AssignmentType, ResultType], ContentGeneratorProtocol):
    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_llm_text(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        wfid: str | None = None,
    ) -> str:
        log.verbose(f"TopCrafter make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-text")
        llm_assignment = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        temporal_client = await self.temporal_client()
        generated_text = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeLLMText.run,
            arg=llm_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated text: {generated_text}")
        return generated_text

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_object_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
        wfid: str | None = None,
    ) -> BaseModelTypeVar:
        log.verbose(f"TopCrafter make_object_direct: {llm_prompt_for_object}")
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-object-direct")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        temporal_client = await self.temporal_client()
        obj = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeObject.run,
            arg=object_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object direct: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_text_then_object(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: LLMPromptFactoryAbstract | None = None,
        wfid: str | None = None,
    ) -> BaseModelTypeVar:
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-text-then-object")

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
        tto_assignment = TextThenObjectAssignment(
            object_class_name=object_class.__name__,
            llm_assignment_for_text=llm_assignment_for_text,
            llm_assignment_factory_to_object=llm_assignment_factory_to_object,
        )

        temporal_client = await self.temporal_client()
        obj = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeTextThenObject.run,
            arg=tto_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object after text: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_object_list_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
        wfid: str | None = None,
    ) -> list[BaseModelTypeVar]:
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-object-list-direct")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        temporal_client = await self.temporal_client()
        obj_list: list[BaseModel] = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeObjectList.run,
            arg=object_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object list direct: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_text_then_object_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: LLMPromptFactoryAbstract | None = None,
        nb_items: int | None = None,
        wfid: str | None = None,
    ) -> list[BaseModelTypeVar]:
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-text-then-object-list")

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
        tto_assignment = TextThenObjectAssignment(
            object_class_name=object_class.__name__,
            llm_assignment_for_text=llm_assignment_for_text,
            llm_assignment_factory_to_object=llm_assignment_factory_to_object,
        )

        temporal_client = await self.temporal_client()
        obj_list: list[BaseModel] = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeTextThenObjectList.run,
            arg=tto_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object list after text: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_single_image(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        wfid: str | None = None,
    ) -> GeneratedImageRawDetails:
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-image")
        img_gen_config = get_config().cogt.img_gen_config
        # We're using workflowWfMakeImages which can generate several images but we're asking for only one
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=1,
        )
        temporal_client = await self.temporal_client()
        generated_image_list = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeImages.run,
            arg=img_gen_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        if len(generated_image_list) != 1:
            msg = f"Expected 1 image, got {len(generated_image_list)}"
            raise ContentGenerationError(msg)
        generated_image = generated_image_list[0]
        log.dev(f"TopCrafter generated image: {generated_image}")
        return generated_image

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_image_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        wfid: str | None = None,
    ) -> list[GeneratedImageRawDetails]:
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-image")
        img_gen_config = get_config().cogt.img_gen_config
        # We're using workflowWfMakeImages which can generate several images but we're asking for only one
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=nb_images,
        )
        temporal_client = await self.temporal_client()
        generated_image_list = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeImages.run,
            arg=img_gen_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.dev(f"TopCrafter generated image list: {generated_image_list}")
        return generated_image_list

    @override
    @with_conditional_worker
    async def make_jinja2_text(
        self,
        context: dict[str, Any],
        jinja2_name: str | None = None,
        jinja2: str | None = None,
        prompting_style: PromptingTarget | None = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
        wfid: str | None = None,
    ) -> str:
        workflow_id = self.make_workflow_id(base_id=wfid or "jinja2-text")
        jinja2_assignment = TemplatingAssignment(
            context=context,
            jinja2_name=jinja2_name,
            jinja2=jinja2,
            prompting_style=prompting_style,
            template_category=template_category,
        )
        temporal_client = await self.temporal_client()
        jinja2_text = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            WfMakeJinja2Text.run,
            arg=jinja2_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
        )
        log.dev(f"TopCrafter jinja2: {jinja2_text}")
        return jinja2_text

    @override
    async def make_extract_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
        wfid: str | None = None,
    ) -> ExtractOutput:
        workflow_id = self.make_workflow_id(base_id=wfid or "extract")
        extract_assignment = ExtractAssignment(
            job_metadata=job_metadata,
            extract_handle=extract_handle,
            extract_input=extract_input,
            extract_job_params=extract_job_params or ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=extract_job_config or ExtractJobConfig(),
        )
        temporal_client = await self.temporal_client()
        extract_output = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeOcr.run,
            arg=extract_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().deep_flow.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.dev(f"TopCrafter extract output: {extract_output}")
        return extract_output
