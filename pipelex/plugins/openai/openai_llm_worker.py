from typing import Any, Optional, Type

import instructor
import openai
from openai import NOT_GIVEN, APIConnectionError, BadRequestError, NotFoundError
from openai.types.chat import ChatCompletionMessage
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMEngineParameterError, LLMModelNotFoundError, SdkTypeError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_func import llm_job_func
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class OpenAILLMWorker(LLMWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod],
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        super().__init__(llm_engine=llm_engine, structure_method=structure_method, report_delegate=report_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            raise SdkTypeError(
                f"Provided LLM sdk_instance for {self.__class__.__name__} is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            )

        self.openai_client_for_text: openai.AsyncOpenAI = sdk_instance
        if structure_method:
            instructor_mode = structure_method.as_instructor_mode()
            log.debug(f"OpenAI structure mode: {structure_method} --> {instructor_mode}")
            self.instructor_for_objects = instructor.from_openai(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = instructor.from_openai(client=sdk_instance)

    #########################################################

    @override
    @llm_job_func
    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        messages = OpenAIFactory.make_simple_messages(
            llm_job=llm_job,
            llm_engine=self.llm_engine,
        )

        try:
            match self.llm_engine.llm_model.llm_family:
                case LLMFamily.O_SERIES:
                    # for o1 models, we must use temperature=1, and tokens limit is named max_completion_tokens
                    response = await self.openai_client_for_text.chat.completions.create(
                        model=self.llm_engine.llm_id,
                        temperature=1,
                        max_completion_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                    )
                case LLMFamily.GEMINI:
                    # for gemini models, we multiply the temperature by 2 because the range is 0-2
                    response = await self.openai_client_for_text.chat.completions.create(
                        model=self.llm_engine.llm_id,
                        temperature=llm_job.job_params.temperature * 2,
                        max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                    )
                case (
                    LLMFamily.GPT_4
                    | LLMFamily.GPT_3_5
                    | LLMFamily.GPT_3
                    | LLMFamily.GPT_4_5
                    | LLMFamily.GPT_4_1
                    | LLMFamily.GPT_4O
                    | LLMFamily.CUSTOM_LLAMA_4
                    | LLMFamily.CUSTOM_GEMMA_3
                    | LLMFamily.CUSTOM_MISTRAL_SMALL_3_1
                    | LLMFamily.CUSTOM_QWEN_3
                    | LLMFamily.PERPLEXITY_SEARCH
                    | LLMFamily.PERPLEXITY_RESEARCH
                    | LLMFamily.PERPLEXITY_REASONING
                    | LLMFamily.PERPLEXITY_DEEPSEEK
                    | LLMFamily.GROK_3
                ):
                    response = await self.openai_client_for_text.chat.completions.create(
                        model=self.llm_engine.llm_id,
                        temperature=llm_job.job_params.temperature,
                        max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                    )
                case (
                    LLMFamily.CLAUDE_3
                    | LLMFamily.CLAUDE_3_5
                    | LLMFamily.CLAUDE_3_7
                    | LLMFamily.CLAUDE_4
                    | LLMFamily.MISTRAL_7B
                    | LLMFamily.MISTRAL_8X7B
                    | LLMFamily.MISTRAL_LARGE
                    | LLMFamily.MISTRAL_SMALL
                    | LLMFamily.MISTRAL_CODESTRAL
                    | LLMFamily.MINISTRAL
                    | LLMFamily.PIXTRAL
                    | LLMFamily.LLAMA_3
                    | LLMFamily.LLAMA_3_1
                    | LLMFamily.BEDROCK_MISTRAL_LARGE
                    | LLMFamily.BEDROCK_ANTHROPIC_CLAUDE
                    | LLMFamily.BEDROCK_META_LLAMA_3
                    | LLMFamily.BEDROCK_AMAZON_NOVA
                ):
                    raise LLMEngineParameterError(f"LLM family {self.llm_engine.llm_model.llm_family} is not supported by OpenAILLMWorker")
        except NotFoundError as not_found_error:
            # TODO: record llm config so it can be displayed here
            raise LLMModelNotFoundError(
                f"OpenAI model or deployment not found:\n{self.llm_engine.desc}\nmodel: {self.llm_engine.llm_model.desc}\n{not_found_error}"
            ) from not_found_error
        except APIConnectionError as api_connection_error:
            raise LLMCompletionError(f"OpenAI API connection error: {api_connection_error}") from api_connection_error
        except BadRequestError as bad_request_error:
            raise LLMCompletionError(
                f"OpenAI bad request error with model: {self.llm_engine.llm_model.desc}:\n{bad_request_error}"
            ) from bad_request_error

        openai_message: ChatCompletionMessage = response.choices[0].message
        response_text = openai_message.content
        if response_text is None:
            print("This helper does not support tools, if we don't get content, something is wrong.")
            raise LLMCompletionError(f"OpenAI response message content is None: {response}\nmodel: {self.llm_engine.llm_model.desc}")

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = OpenAIFactory.make_nb_tokens_by_category(usage=usage)
        return response_text

    @override
    @llm_job_func
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        messages = OpenAIFactory.make_simple_messages(
            llm_job=llm_job,
            llm_engine=self.llm_engine,
        )
        try:
            match self.llm_engine.llm_model.llm_family:
                case LLMFamily.O_SERIES:
                    # for o1 models, we must use temperature=1, and tokens limit is named max_completion_tokens
                    result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                        model=self.llm_engine.llm_id,
                        temperature=1,
                        max_completion_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                        response_model=schema,
                        max_retries=llm_job.job_config.max_retries,
                    )
                case LLMFamily.GEMINI:
                    # for gemini models, we multiply the temperature by 2 because the range is 0-2
                    result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                        model=self.llm_engine.llm_id,
                        temperature=llm_job.job_params.temperature * 2,
                        max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                        response_model=schema,
                        max_retries=llm_job.job_config.max_retries,
                    )
                case (
                    LLMFamily.GPT_4
                    | LLMFamily.GPT_3_5
                    | LLMFamily.GPT_3
                    | LLMFamily.GPT_4_5
                    | LLMFamily.GPT_4_1
                    | LLMFamily.GPT_4O
                    | LLMFamily.CUSTOM_LLAMA_4
                    | LLMFamily.CUSTOM_GEMMA_3
                    | LLMFamily.CUSTOM_MISTRAL_SMALL_3_1
                    | LLMFamily.CUSTOM_QWEN_3
                    | LLMFamily.PERPLEXITY_SEARCH
                    | LLMFamily.PERPLEXITY_RESEARCH
                    | LLMFamily.PERPLEXITY_REASONING
                    | LLMFamily.PERPLEXITY_DEEPSEEK
                    | LLMFamily.GROK_3
                ):
                    result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                        model=self.llm_engine.llm_id,
                        temperature=llm_job.job_params.temperature,
                        max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                        response_model=schema,
                        max_retries=llm_job.job_config.max_retries,
                    )
                case (
                    LLMFamily.CLAUDE_3
                    | LLMFamily.CLAUDE_3_5
                    | LLMFamily.CLAUDE_3_7
                    | LLMFamily.CLAUDE_4
                    | LLMFamily.MISTRAL_7B
                    | LLMFamily.MISTRAL_8X7B
                    | LLMFamily.MISTRAL_LARGE
                    | LLMFamily.MISTRAL_SMALL
                    | LLMFamily.MISTRAL_CODESTRAL
                    | LLMFamily.MINISTRAL
                    | LLMFamily.PIXTRAL
                    | LLMFamily.LLAMA_3
                    | LLMFamily.LLAMA_3_1
                    | LLMFamily.BEDROCK_MISTRAL_LARGE
                    | LLMFamily.BEDROCK_ANTHROPIC_CLAUDE
                    | LLMFamily.BEDROCK_META_LLAMA_3
                    | LLMFamily.BEDROCK_AMAZON_NOVA
                ):
                    raise LLMEngineParameterError(f"LLM family {self.llm_engine.llm_model.llm_family} is not supported by OpenAILLMWorker")
        except NotFoundError as exc:
            raise LLMCompletionError(f"OpenAI model or deployment '{self.llm_engine.llm_id}' not found: {exc}") from exc
        except BadRequestError as bad_request_error:
            raise LLMCompletionError(
                f"OpenAI bad request error with model: {self.llm_engine.llm_model.desc}:\n{bad_request_error}"
            ) from bad_request_error

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = OpenAIFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
