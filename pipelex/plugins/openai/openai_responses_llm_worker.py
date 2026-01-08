from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import instructor
import openai
from instructor.exceptions import InstructorRetryException
from openai import NOT_GIVEN, APIConnectionError, AuthenticationError, BadRequestError, NotFoundError, omit
from typing_extensions import override

from pipelex.cogt.exceptions import LLMCompletionError, LLMModelNotFoundError, SdkTypeError
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.config import get_config
from pipelex.system.telemetry.otel_constants import InferenceOutputType

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory
    from pipelex.reporting.reporting_protocol import ReportingProtocol
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class OpenAIResponsesLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        openai_responses_factory: OpenAIResponsesFactory,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            msg = f"Provided LLM sdk_instance for {self.__class__.__name__} is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.openai_client_for_responses: openai.AsyncOpenAI = sdk_instance
        self.openai_responses_factory = openai_responses_factory

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

    #########################################################
    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        input_items = await self.openai_responses_factory.make_input_items(llm_job=llm_job)
        try:
            extra_headers, extra_body = self.openai_responses_factory.make_extras(
                inference_model=self.inference_model, inference_job=llm_job, output_desc=InferenceOutputType.TEXT
            )
            response = await self.openai_client_for_responses.responses.create(
                model=self.inference_model.model_id,
                instructions=llm_job.llm_prompt.system_text,
                temperature=job_params.temperature,
                max_output_tokens=job_params.max_tokens or omit,
                input=input_items,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
        except NotFoundError as not_found_error:
            msg = (
                f"OpenAI Responses model or deployment not found:\n{self.inference_model.desc}\nmodel: {self.inference_model.desc}\n{not_found_error}"
            )
            raise LLMModelNotFoundError(message=msg, model_handle=self.inference_model.name) from not_found_error
        except APIConnectionError as api_connection_error:
            msg = f"OpenAI API connection error: {api_connection_error}"
            raise LLMCompletionError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"OpenAI bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error
        except AuthenticationError as authentication_error:
            msg = f"Authentication error: {authentication_error}"
            raise LLMCompletionError(msg) from authentication_error

        if not response.output_text:
            msg = f"OpenAI Responses message content is empty: {response}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and response.usage:
            llm_tokens_usage.nb_tokens_by_category = self.openai_responses_factory.make_nb_tokens_by_category(usage=response.usage)
        return response.output_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        try:
            if not hasattr(self.instructor_for_objects, "responses"):
                msg = "Instructor client is not configured for the Responses API. Set a responses-capable structure_method for this model."
                raise LLMCompletionError(msg)
            extra_headers, extra_body = self.openai_responses_factory.make_extras(
                inference_model=self.inference_model, inference_job=llm_job, output_desc=schema.__name__
            )
            input_items = await self.openai_responses_factory.make_input_items(llm_job=llm_job)
            result_object, completion = await self.instructor_for_objects.responses.create_with_completion(  # pyright: ignore[reportUnknownMemberType]
                input=cast("list[ChatCompletionMessageParam]", input_items),
                response_model=schema,
                max_retries=llm_job.job_config.max_retries,
                model=self.inference_model.model_id,
                instructions=llm_job.llm_prompt.system_text,
                temperature=job_params.temperature,
                max_output_tokens=job_params.max_tokens or NOT_GIVEN,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )  # type: ignore[arg-type,misc]
        except InstructorRetryException as exc:
            msg = f"OpenAI instructor failed with model: {self.inference_model.desc} trying to generate schema: {schema} with error: {exc}"
            raise LLMCompletionError(msg) from exc
        except NotFoundError as exc:
            msg = f"OpenAI Responses model or deployment '{self.inference_model.model_id}' not found: {exc}"
            raise LLMCompletionError(msg) from exc
        except BadRequestError as bad_request_error:
            msg = f"OpenAI bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error
        except AuthenticationError as authentication_error:
            msg = f"Authentication error: {authentication_error}"
            raise LLMCompletionError(msg) from authentication_error

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and hasattr(completion, "usage"):
            completion_usage = completion.usage
            if completion_usage:
                llm_tokens_usage.nb_tokens_by_category = self.openai_responses_factory.make_nb_tokens_by_category(usage=completion_usage)

        typed_result_object: BaseModelTypeVar = result_object
        return typed_result_object
