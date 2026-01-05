from typing import TYPE_CHECKING, Any

import instructor
from mistralai import Mistral

if TYPE_CHECKING:
    from mistralai.models import ChatCompletionResponse
from typing_extensions import override

from pipelex.cogt.exceptions import LLMCompletionError, SdkTypeError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.mistral.mistral_exceptions import MistralWorkerConfigurationError
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class MistralLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        mistral_factory: MistralFactory,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
            self,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )

        if not isinstance(sdk_instance, Mistral):
            msg = f"Provided LLM sdk_instance for {self.__class__.__name__} is not of type Mistral: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        if default_max_tokens := inference_model.max_tokens:
            self.default_max_tokens = default_max_tokens
        else:
            msg = f"No max_tokens provided for llm model '{self.inference_model.desc}', but it is required for Mistral"
            raise MistralWorkerConfigurationError(msg)
        self.mistral_client_for_text: Mistral = sdk_instance
        self.mistral_factory = mistral_factory

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = instructor.from_mistral(client=sdk_instance, mode=instructor_mode, use_async=True)
        else:
            self.instructor_for_objects = instructor.from_mistral(client=sdk_instance, use_async=True)

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.mistral_factory.make_simple_messages(llm_job=llm_job)
        response: ChatCompletionResponse | None = await self.mistral_client_for_text.chat.complete_async(
            messages=messages,
            model=self.inference_model.model_id,
            temperature=job_params.temperature,
            max_tokens=job_params.max_tokens or self.default_max_tokens,
        )
        if not response:
            msg = "Mistral response is None"
            raise LLMCompletionError(msg)
        if not response.choices:
            msg = "Mistral response.choices is None"
            raise LLMCompletionError(msg)
        mistral_response_content = response.choices[0].message.content
        if not isinstance(mistral_response_content, str):
            msg = "Mistral response.choices[0].message.content is not a string"
            raise LLMCompletionError(msg)

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = self.mistral_factory.make_nb_tokens_by_category(usage=usage)

        return mistral_response_content

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.mistral_factory.make_simple_messages_openai_typed(llm_job=llm_job)
        result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
            response_model=schema,
            messages=messages,
            model=self.inference_model.model_id,
            temperature=job_params.temperature,
            max_tokens=job_params.max_tokens or self.default_max_tokens,
        )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = self.mistral_factory.make_nb_tokens_by_category(usage=usage)

        return result_object
