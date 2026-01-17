from typing import TYPE_CHECKING, Any

import instructor
import openai
from instructor.exceptions import InstructorRetryException
from openai import NOT_GIVEN, APIConnectionError, AuthenticationError, BadRequestError, NotFoundError, omit
from typing_extensions import override

from pipelex.cogt.exceptions import LLMCompletionError, SdkTypeError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.telemetry.otel_constants import InferenceOutputType
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessage


class OpenAICompletionsLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        openai_completions_factory: OpenAICompletionsFactory,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
            self,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            msg = f"Provided LLM sdk_instance for {self.__class__.__name__} is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.openai_client_for_text: openai.AsyncOpenAI = sdk_instance
        self.openai_completions_factory = openai_completions_factory
        if instructor_mode := self.inference_model.get_instructor_mode():
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
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.openai_completions_factory.make_simple_messages(llm_job=llm_job)

        try:
            extra_headers, extra_body = self.openai_completions_factory.make_extras(
                inference_model=self.inference_model, inference_job=llm_job, output_desc=InferenceOutputType.TEXT
            )
            response = await self.openai_client_for_text.chat.completions.create(
                model=self.inference_model.model_id,
                temperature=job_params.temperature,
                max_tokens=job_params.max_tokens or omit,
                seed=job_params.seed,
                messages=messages,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
        except NotFoundError as exc:
            msg = f"LLM model or deployment '{self.inference_model.model_id}' not found: {exc}"
            raise LLMCompletionError(msg) from exc
        except APIConnectionError as api_connection_error:
            msg = f"LLM API connection error: {api_connection_error}"
            raise LLMCompletionError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"LLM bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error
        except AuthenticationError as authentication_error:
            msg = f"LLM authentication error: {authentication_error}"
            raise LLMCompletionError(msg) from authentication_error

        if not response.choices:
            msg = f"OpenAI chat completion response choices are empty with model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        openai_message: ChatCompletionMessage = response.choices[0].message
        response_text = openai_message.content
        if response_text is None:
            msg = f"OpenAI response message content is None: {response}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = self.openai_completions_factory.make_nb_tokens_by_category(usage=usage)
        return response_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.openai_completions_factory.make_simple_messages(llm_job=llm_job)
        try:
            try:
                extra_headers, extra_body = self.openai_completions_factory.make_extras(
                    inference_model=self.inference_model, inference_job=llm_job, output_desc=schema.__name__
                )
                result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                    model=self.inference_model.model_id,
                    temperature=job_params.temperature,
                    max_tokens=job_params.max_tokens or NOT_GIVEN,
                    seed=job_params.seed,
                    messages=messages,
                    response_model=schema,
                    max_retries=llm_job.job_config.max_retries,
                    extra_headers=extra_headers,
                    extra_body=extra_body,
                )
            except InstructorRetryException as exc:
                msg = (
                    f"LLM structured generation via 'instructor' failed with model: {self.inference_model.desc} "
                    f"trying to generate schema: {schema} with error: {exc}"
                )
                raise LLMCompletionError(msg) from exc
        except NotFoundError as exc:
            msg = f"LLM model or deployment '{self.inference_model.model_id}' not found: {exc}"
            raise LLMCompletionError(msg) from exc
        except APIConnectionError as api_connection_error:
            msg = f"LLM API connection error: {api_connection_error}"
            raise LLMCompletionError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"LLM bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error
        except AuthenticationError as authentication_error:
            msg = f"LLM authentication error: {authentication_error}"
            raise LLMCompletionError(msg) from authentication_error

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = self.openai_completions_factory.make_nb_tokens_by_category(usage=usage)

        return result_object
