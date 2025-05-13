# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Optional, Type

import instructor
from anthropic import NOT_GIVEN, AsyncAnthropic, AsyncAnthropicBedrock
from typing_extensions import override

from pipelex import log
from pipelex.cogt.anthropic.anthropic_factory import AnthropicFactory
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract, llm_job_func
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.tools.misc.model_helpers import BaseModelType


class AnthropicWorker(LLMWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod] = None,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        LLMWorkerAbstract.__init__(
            self,
            llm_engine=llm_engine,
            structure_method=structure_method,
            report_delegate=report_delegate,
        )
        if default_max_tokens := llm_engine.llm_model.max_tokens:
            self.default_max_tokens = default_max_tokens
        else:
            raise ValueError("max_tokens is None, which is required for Anthropic models")

        # Verify if the sdk_instance is compatible with the current LLM platform
        if isinstance(sdk_instance, (AsyncAnthropic, AsyncAnthropicBedrock)):
            if llm_engine.llm_platform == LLMPlatform.ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropic)):
                raise ValueError(f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}")
            elif llm_engine.llm_platform == LLMPlatform.BEDROCK_ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropicBedrock)):
                raise ValueError(f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}")
        else:
            raise ValueError(f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}")

        self.anthropic_async_client = sdk_instance
        if structure_method:
            instructor_mode = structure_method.as_instructor_mode()
            log.debug(f"Anthropic structure mode: {structure_method} --> {instructor_mode}")
            self.instructor_for_objects = instructor.from_anthropic(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = instructor.from_anthropic(client=sdk_instance)

    #########################################################
    # Instance methods
    #########################################################

    @override
    @llm_job_func
    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        message = await AnthropicFactory.make_user_message(llm_job=llm_job)
        response = await self.anthropic_async_client.messages.create(
            messages=[message],
            system=llm_job.llm_prompt.system_text or NOT_GIVEN,
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=llm_job.job_params.max_tokens or self.default_max_tokens,
        )

        single_content_block = response.content[0]
        if single_content_block.type != "text":
            raise ValueError(f"Unexpected content block type: {single_content_block.type}")
        full_reply_content = single_content_block.text

        single_content_block = response.content[0]
        if single_content_block.type != "text":
            raise ValueError(f"Unexpected content block type: {single_content_block.type}")
        full_reply_content = single_content_block.text

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return full_reply_content

    @override
    @llm_job_func
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelType],
    ) -> BaseModelType:
        messages = await AnthropicFactory.make_simple_messages(llm_job=llm_job)
        result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
            messages=messages,
            response_model=schema,
            max_retries=llm_job.job_config.max_retries,
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=llm_job.job_params.max_tokens or self.default_max_tokens,
        )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
