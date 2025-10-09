from typing import TYPE_CHECKING, Any

import instructor
import openai
from instructor.exceptions import InstructorRetryException
from openai import NOT_GIVEN, APIConnectionError, BadRequestError, NotFoundError

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessage
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMModelNotFoundError, SdkTypeError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class OpenAILLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        structure_method: StructureMethod | None,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
            self,
            inference_model=inference_model,
            structure_method=structure_method,
            reporting_delegate=reporting_delegate,
        )

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            msg = f"Provided LLM sdk_instance for {self.__class__.__name__} is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.openai_client_for_text: openai.AsyncOpenAI = sdk_instance
        if structure_method:
            instructor_mode = structure_method.as_instructor_mode()
            log.debug(f"OpenAI structure mode: {structure_method} --> {instructor_mode}")
            self.instructor_for_objects = instructor.from_openai(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = instructor.from_openai(client=sdk_instance)

        instructor_config = get_config().cogt.llm_config.instructor_config
        if instructor_config.is_dump_kwargs_enabled:
            self.instructor_for_objects.on(hook_name="completion:kwargs", handler=dump_kwargs)
        if instructor_config.is_dump_response_enabled:
            self.instructor_for_objects.on(hook_name="completion:response", handler=dump_response_from_structured_gen)
        if instructor_config.is_dump_error_enabled:
            self.instructor_for_objects.on(hook_name="completion:error", handler=dump_error)

    #########################################################
    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        pass

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        messages = OpenAIFactory.make_simple_messages(llm_job=llm_job)

        try:
            temperature = llm_job.job_params.temperature
            if ModelConstraints.TEMPERATURE_MUST_BE_MULTIPLIED_BY_2 in self.inference_model.constraints:
                temperature *= 2
            if ModelConstraints.TEMPERATURE_MUST_BE_1 in self.inference_model.constraints and temperature != 1:
                log.warning(f"OpenAI model {self.inference_model.desc} used with a temperature of {temperature}, but it must be 1 for this model")
                temperature = 1
            response = await self.openai_client_for_text.chat.completions.create(
                model=self.inference_model.model_id,
                temperature=temperature,
                max_tokens=llm_job.job_params.max_tokens or None,
                seed=llm_job.job_params.seed,
                messages=messages,
            )
        except NotFoundError as not_found_error:
            # TODO: record llm config so it can be displayed here
            msg = f"OpenAI model or deployment not found:\n{self.inference_model.desc}\nmodel: {self.inference_model.desc}\n{not_found_error}"
            raise LLMModelNotFoundError(msg) from not_found_error
        except APIConnectionError as api_connection_error:
            msg = f"OpenAI API connection error: {api_connection_error}"
            raise LLMCompletionError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"OpenAI bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error

        openai_message: ChatCompletionMessage = response.choices[0].message
        response_text = openai_message.content
        if response_text is None:
            msg = f"OpenAI response message content is None: {response}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = OpenAIFactory.make_nb_tokens_by_category(usage=usage)
        return response_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        messages = OpenAIFactory.make_simple_messages(llm_job=llm_job)
        try:
            temperature = llm_job.job_params.temperature
            if ModelConstraints.TEMPERATURE_MUST_BE_MULTIPLIED_BY_2 in self.inference_model.constraints:
                temperature *= 2
            if ModelConstraints.TEMPERATURE_MUST_BE_1 in self.inference_model.constraints and temperature != 1:
                log.warning(f"OpenAI model {self.inference_model.desc} used with a temperature of {temperature}, but it must be 1 for this model")
                temperature = 1
            try:
                result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                    model=self.inference_model.model_id,
                    temperature=temperature,
                    max_tokens=llm_job.job_params.max_tokens or NOT_GIVEN,
                    seed=llm_job.job_params.seed,
                    messages=messages,
                    response_model=schema,
                    max_retries=llm_job.job_config.max_retries,
                )
            except InstructorRetryException as exc:
                msg = f"OpenAI instructor failed with model: {self.inference_model.desc} trying to generate schema: {schema} with error: {exc}"
                raise LLMCompletionError(msg) from exc
        except NotFoundError as exc:
            msg = f"OpenAI model or deployment '{self.inference_model.model_id}' not found: {exc}"
            raise LLMCompletionError(msg) from exc
        except BadRequestError as bad_request_error:
            msg = f"OpenAI bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = OpenAIFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
