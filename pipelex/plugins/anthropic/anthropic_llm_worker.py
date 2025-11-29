from typing import Any

import instructor
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock, omit
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import LLMCompletionError, SdkTypeError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_utils import (
    dump_error,
    dump_kwargs,
    dump_response_from_structured_gen,
)
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.anthropic.anthropic_exceptions import (
    AnthropicWorkerConfigurationError,
)
from pipelex.plugins.anthropic.anthropic_factory import (
    AnthropicFactory,
    AnthropicSdkVariant,
)
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class AnthropicLLMWorkerError(PipelexError):
    """Base exception for Anthropic LLM Worker errors."""


class AnthropicBadRequestError(AnthropicLLMWorkerError):
    """Raised when Anthropic API returns a BadRequestError."""


class AnthropicInstructorError(AnthropicLLMWorkerError):
    """Raised when Instructor encounters an error with Anthropic."""


class AnthropicLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
            self,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        self.extra_config: dict[str, Any] = extra_config
        self.default_max_tokens: int = 0
        if inference_model.max_tokens:
            self.default_max_tokens = inference_model.max_tokens
        else:
            msg = f"No max_tokens provided for llm model '{self.inference_model.desc}', but it is required for Anthropic"
            raise AnthropicWorkerConfigurationError(msg)

        # Verify if the sdk_instance is compatible with the current LLM platform
        if isinstance(sdk_instance, (AsyncAnthropic, AsyncAnthropicBedrock)):
            if (inference_model.sdk == AnthropicSdkVariant.ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropic))) or (
                inference_model.sdk == AnthropicSdkVariant.BEDROCK_ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropicBedrock))
            ):
                msg = f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}"
                raise SdkTypeError(msg)
        else:
            msg = f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}"
            raise SdkTypeError(msg)

        self.anthropic_async_client = sdk_instance
        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = instructor.from_anthropic(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = instructor.from_anthropic(client=sdk_instance)

        instructor_config = get_config().cogt.llm_config.instructor_config
        if instructor_config.is_dump_kwargs_enabled:
            self.instructor_for_objects.on(hook_name="completion:kwargs", handler=dump_kwargs)
        if instructor_config.is_dump_response_enabled:
            self.instructor_for_objects.on(
                hook_name="completion:response",
                handler=dump_response_from_structured_gen,
            )
        if instructor_config.is_dump_error_enabled:
            self.instructor_for_objects.on(hook_name="completion:error", handler=dump_error)

    #########################################################
    # Instance methods
    #########################################################

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        message = await AnthropicFactory.make_user_message(llm_job=llm_job)
        response = await self.anthropic_async_client.messages.create(
            messages=[message],
            system=llm_job.llm_prompt.system_text or omit,
            model=self.inference_model.model_id,
            temperature=job_params.temperature,
            max_tokens=job_params.max_tokens or self.default_max_tokens,
        )

        single_content_block = response.content[0]
        if single_content_block.type != "text":
            msg = f"Unexpected content block type: {single_content_block.type}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(msg)
        full_reply_content = single_content_block.text

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return full_reply_content

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await AnthropicFactory.make_simple_messages(llm_job=llm_job)
        (
            result_object,
            completion,
        ) = await self.instructor_for_objects.chat.completions.create_with_completion(
            messages=messages,
            response_model=schema,
            max_retries=llm_job.job_config.max_retries,
            model=self.inference_model.model_id,
            temperature=job_params.temperature,
            max_tokens=job_params.max_tokens or self.default_max_tokens,
        )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
