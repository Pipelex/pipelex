from typing import TYPE_CHECKING, Any

import openai
from openai import (
    NOT_GIVEN,
    omit,
)
from openai.types.chat import ChatCompletionReasoningEffort
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCapabilityError, LLMCompletionError, SdkTypeError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_underlying_sdk_exception,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.plugins.openai.openai_error_classification import classify_openai_sdk_error
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
        from instructor import from_openai  # noqa: PLC0415

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_openai(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = from_openai(client=sdk_instance)

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
    # Reasoning helpers
    #########################################################

    def _resolve_reasoning_effort(self, job_params: LLMJobParams) -> ChatCompletionReasoningEffort | None:
        """Resolve reasoning parameters to an OpenAI Chat Completions reasoning_effort value.

        Args:
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.

        Returns:
            The OpenAI reasoning_effort string, or None if reasoning is not requested.

        """
        thinking_mode = self.inference_model.thinking_mode

        if job_params.reasoning_effort is not None:
            effort = job_params.reasoning_effort
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    openai_effort = get_config().cogt.llm_config.openai_config.get_reasoning_level(effort=effort)
                    log.verbose(f"OpenAI Chat Completions reasoning_effort={openai_effort}")
                    return openai_effort
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{self.inference_model.desc}' has thinking_mode=adaptive which is not supported by the OpenAI Chat Completions API"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.NONE:
                    msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                    raise LLMCapabilityError(msg)

        if job_params.reasoning_budget is not None:
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    msg = f"Model '{self.inference_model.desc}' does not support reasoning_budget; OpenAI uses reasoning_effort instead"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{self.inference_model.desc}' has thinking_mode=adaptive which is not supported by the OpenAI Chat Completions API"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.NONE:
                    msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                    raise LLMCapabilityError(msg)

        return None

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.openai_completions_factory.make_simple_messages(llm_job=llm_job)

        openai_reasoning_effort = self._resolve_reasoning_effort(job_params=job_params)

        try:
            extra_headers, extra_body = self.openai_completions_factory.make_extras(
                inference_model=self.inference_model, inference_job=llm_job, output_desc=InferenceOutputType.TEXT
            )
            temperature_unsupported = ListedConstraint.TEMPERATURE_UNSUPPORTED in self.inference_model.listed_constraints
            response = await self.openai_client_for_text.chat.completions.create(
                model=self.inference_model.model_id,
                temperature=omit if (openai_reasoning_effort is not None or temperature_unsupported) else job_params.temperature,
                max_tokens=job_params.max_tokens or omit,
                seed=job_params.seed,
                messages=messages,
                reasoning_effort=openai_reasoning_effort if openai_reasoning_effort is not None else omit,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
        except (openai.APIStatusError, openai.APIConnectionError) as sdk_exc:
            categorized = classify_openai_sdk_error(
                sdk_exc=sdk_exc,
                model_desc=self.inference_model.desc,
                model_id=self.inference_model.model_id,
                model_handle=self.inference_model.name,
            )
            if categorized is None:
                raise  # defensive: every caught type is recognized by the classifier
            raise categorized from sdk_exc

        if not response.choices:
            msg = f"OpenAI chat completion response choices are empty with model: {self.inference_model.desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="OpenAI returned no completion choices — try rephrasing the prompt or using a different model",
                ),
            )

        finish_reason = response.choices[0].finish_reason
        if finish_reason == "content_filter":
            msg = f"OpenAI response was filtered by content policy for model: {self.inference_model.desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Content was rejected by safety filters — revise the prompt",
                ),
            )

        openai_message: ChatCompletionMessage = response.choices[0].message
        response_text = openai_message.content
        if response_text is None:
            msg = f"OpenAI response message content is None: {response}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="OpenAI returned a response with no content — try rephrasing the prompt or using a different model",
                ),
            )

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
        self._validate_no_reasoning_for_structured_gen(job_params=job_params)
        messages = await self.openai_completions_factory.make_simple_messages(llm_job=llm_job)
        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # noqa: PLC0415

        extra_headers, extra_body = self.openai_completions_factory.make_extras(
            inference_model=self.inference_model, inference_job=llm_job, output_desc=schema.__name__
        )
        temperature_unsupported = ListedConstraint.TEMPERATURE_UNSUPPORTED in self.inference_model.listed_constraints
        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                model=self.inference_model.model_id,
                temperature=omit if temperature_unsupported else job_params.temperature,
                max_tokens=job_params.max_tokens or NOT_GIVEN,
                seed=job_params.seed,
                messages=messages,
                response_model=schema,
                # instructor's max_retries retries schema-validation failures only, not transport errors —
                # transient transport retry is the PipeRouter's job, not this call's.
                max_retries=llm_job.job_config.max_retries,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            categorized = (
                classify_openai_sdk_error(
                    sdk_exc=underlying_exc,
                    model_desc=self.inference_model.desc,
                    model_id=self.inference_model.model_id,
                    model_handle=self.inference_model.name,
                )
                if underlying_exc is not None
                else None
            )
            if categorized is not None:
                raise categorized from instructor_exc
            msg = (
                f"OpenAI structured generation via 'instructor' failed with model: {self.inference_model.desc} "
                f"trying to generate schema: {schema} with error: {instructor_exc}"
            )
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.UNKNOWN) from instructor_exc
        except (openai.APIStatusError, openai.APIConnectionError) as sdk_exc:
            categorized = classify_openai_sdk_error(
                sdk_exc=sdk_exc,
                model_desc=self.inference_model.desc,
                model_id=self.inference_model.model_id,
                model_handle=self.inference_model.name,
            )
            if categorized is None:
                raise  # defensive: every caught type is recognized by the classifier
            raise categorized from sdk_exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = self.openai_completions_factory.make_nb_tokens_by_category(usage=usage)

        return result_object
