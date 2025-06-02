from typing import Any, Optional, Type

import instructor
from mistralai import Mistral
from mistralai.models import ChatCompletionResponse
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMEngineParameterError, SdkTypeError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_func import llm_job_func
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class MistralLLMWorker(LLMWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod] = None,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        super().__init__(llm_engine=llm_engine, structure_method=structure_method, report_delegate=report_delegate)

        if not isinstance(sdk_instance, Mistral):
            raise SdkTypeError(f"Provided LLM sdk_instance for {self.__class__.__name__} is not of type Mistral: it's a '{type(sdk_instance)}'")

        if default_max_tokens := llm_engine.llm_model.max_tokens:
            self.default_max_tokens = default_max_tokens
        else:
            raise LLMEngineParameterError(f"No max_tokens provided for llm model '{self.llm_engine.llm_model.desc}', but it is required for Mistral")
        self.mistral_client_for_text: Mistral = sdk_instance

        if structure_method:
            instructor_mode = structure_method.as_instructor_mode()
            log.debug(f"Mistral structure mode: {structure_method} --> {instructor_mode}")
            self.instructor_for_objects = instructor.from_mistral(client=sdk_instance, mode=instructor_mode, use_async=True)
        else:
            self.instructor_for_objects = instructor.from_mistral(client=sdk_instance, use_async=True)

    @override
    @llm_job_func
    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        messages = MistralFactory.make_simple_messages(llm_job=llm_job)
        response: Optional[ChatCompletionResponse] = await self.mistral_client_for_text.chat.complete_async(
            messages=messages,
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=llm_job.job_params.max_tokens or self.default_max_tokens,
        )
        if not response:
            raise LLMCompletionError("Mistral response is None")
        if not response.choices:
            raise LLMCompletionError("Mistral response.choices is None")
        mistral_response_content = response.choices[0].message.content
        if not isinstance(mistral_response_content, str):
            raise LLMCompletionError("Mistral response.choices[0].message.content is not a string")

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = MistralFactory.make_nb_tokens_by_category(usage=usage)

        return mistral_response_content

    @override
    @llm_job_func
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
            response_model=schema,
            messages=MistralFactory.make_simple_messages_openai_typed(llm_job=llm_job),
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=llm_job.job_params.max_tokens or self.default_max_tokens,
        )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = MistralFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
