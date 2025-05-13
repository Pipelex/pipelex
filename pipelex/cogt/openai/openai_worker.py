# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Optional, Type

import instructor
import openai
from openai import NOT_GIVEN, NotFoundError
from openai.types.chat import ChatCompletionMessage
from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract, llm_job_func
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.openai.openai_errors import OpenAIWorkerError
from pipelex.cogt.openai.openai_factory import OpenAIFactory
from pipelex.tools.misc.model_helpers import BaseModelType


class OpenAIWorker(LLMWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod],
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        super().__init__(llm_engine=llm_engine, structure_method=structure_method, report_delegate=report_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            raise ValueError(f"openai_sdk_instance is not of type openai.OpenAI: {sdk_instance}")

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
                case _:
                    response = await self.openai_client_for_text.chat.completions.create(
                        model=self.llm_engine.llm_id,
                        temperature=llm_job.job_params.temperature,
                        max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                    )
        except NotFoundError as exc:
            raise OpenAIWorkerError(f"OpenAI model or deployment '{self.llm_engine.llm_id}' not found: {exc}") from exc

        openai_message: ChatCompletionMessage = response.choices[0].message
        response_text = openai_message.content
        if response_text is None:
            print("This helper does not support tools, if we don't get content, something is wrong.")
            raise ValueError(f"OpenAI response message content is None: {response}")

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = OpenAIFactory.make_nb_tokens_by_category(usage=usage)
        return response_text

    @override
    @llm_job_func
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelType],
    ) -> BaseModelType:
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
                case _:
                    result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                        model=self.llm_engine.llm_id,
                        temperature=llm_job.job_params.temperature,
                        max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                        seed=llm_job.job_params.seed,
                        messages=messages,
                        response_model=schema,
                        max_retries=llm_job.job_config.max_retries,
                    )
        except NotFoundError as exc:
            raise OpenAIWorkerError(f"OpenAI model or deployment '{self.llm_engine.llm_id}' not found: {exc}") from exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = OpenAIFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
