from typing import Any, Optional, Type

import instructor
from anthropic import NOT_GIVEN, AsyncAnthropic, AsyncAnthropicBedrock
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMEngineParameterError, SdkTypeError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_func import llm_job_func
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.config import get_config
from pipelex.plugins.anthropic.anthropic_factory import AnthropicFactory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class AnthropicLLMWorker(LLMWorkerAbstract):
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
        self.default_max_tokens: int
        if default_max_tokens := llm_engine.llm_model.max_tokens:
            self.default_max_tokens = default_max_tokens
        else:
            raise LLMEngineParameterError(
                f"No max_tokens provided for llm model '{self.llm_engine.llm_model.desc}', but it is required for Anthropic"
            )

        # Verify if the sdk_instance is compatible with the current LLM platform
        if isinstance(sdk_instance, (AsyncAnthropic, AsyncAnthropicBedrock)):
            if llm_engine.llm_platform == LLMPlatform.ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropic)):
                raise SdkTypeError(f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}")
            elif llm_engine.llm_platform == LLMPlatform.BEDROCK_ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropicBedrock)):
                raise SdkTypeError(f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}")
        else:
            raise SdkTypeError(f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}")

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

    # TODO: implement streaming behind the scenes to avoid timeout/streaming errors with Claude 4 and high tokens
    def _adapt_max_tokens(self, max_tokens: Optional[int]) -> int:
        max_tokens = max_tokens or self.default_max_tokens
        if claude_4_tokens_limit := get_config().plugins.anthropic_config.claude_4_tokens_limit:
            if max_tokens > claude_4_tokens_limit:
                max_tokens = claude_4_tokens_limit
                log.warning(f"Max tokens is greater than the claude 4 reduced tokens limit, reducing to {max_tokens}")
        return max_tokens

    @override
    @llm_job_func
    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        message = await AnthropicFactory.make_user_message(llm_job=llm_job)
        max_tokens = self._adapt_max_tokens(max_tokens=llm_job.job_params.max_tokens)
        response = await self.anthropic_async_client.messages.create(
            messages=[message],
            system=llm_job.llm_prompt.system_text or NOT_GIVEN,
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=max_tokens,
        )

        single_content_block = response.content[0]
        if single_content_block.type != "text":
            raise LLMCompletionError(f"Unexpected content block type: {single_content_block.type}\nmodel: {self.llm_engine.llm_model.desc}")
        full_reply_content = single_content_block.text

        single_content_block = response.content[0]
        if single_content_block.type != "text":
            raise LLMCompletionError(f"Unexpected content block type: {single_content_block.type}\nmodel: {self.llm_engine.llm_model.desc}")
        full_reply_content = single_content_block.text

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return full_reply_content

    @override
    @llm_job_func
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        messages = await AnthropicFactory.make_simple_messages(llm_job=llm_job)
        max_tokens = self._adapt_max_tokens(max_tokens=llm_job.job_params.max_tokens)
        result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
            messages=messages,
            response_model=schema,
            max_retries=llm_job.job_config.max_retries,
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=max_tokens,
        )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
