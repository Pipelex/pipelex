from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import openai
from openai import (
    NOT_GIVEN,
    omit,
)
from openai.types.shared_params import Reasoning
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import (
    InferenceErrorCategory,
    LLMCapabilityError,
    LLMCompletionError,
    SdkTypeError,
)
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_openai_metadata,
    extract_underlying_sdk_exception,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.config import get_config
from pipelex.system.telemetry.otel_constants import InferenceOutputType

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.llm.llm_job_components import LLMJobParams
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
    from pipelex.reporting.reporting_protocol import ReportingProtocol
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class OpenAIResponsesLLMWorker(LLMWorkerAbstract):
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
        from instructor import from_openai  # ruff: ignore[import-outside-top-level]

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_openai(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = from_openai(client=sdk_instance)

        instructor_config = get_config().inference.llm.instructor
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

    def _resolve_reasoning(self, job_params: LLMJobParams) -> Reasoning | None:
        """Resolve reasoning parameters to an OpenAI Responses API reasoning dict.

        Args:
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.

        Returns:
            A Reasoning dict for the OpenAI Responses API, or None if reasoning is not requested.

        """
        thinking_mode = self.inference_model.thinking_mode

        if job_params.reasoning_effort is not None:
            effort = job_params.reasoning_effort
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    openai_effort = get_config().inference.llm.openai.get_reasoning_level(effort=effort)
                    if openai_effort is None:
                        return None
                    log.verbose(f"OpenAI Responses reasoning effort={openai_effort}")
                    return Reasoning(effort=openai_effort)
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{self.inference_model.desc}' has thinking_mode=adaptive which is not supported by the OpenAI Responses API"
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
                    msg = f"Model '{self.inference_model.desc}' has thinking_mode=adaptive which is not supported by the OpenAI Responses API"
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
        input_items = await self.openai_responses_factory.make_input_items(llm_job=llm_job)

        openai_reasoning = self._resolve_reasoning(job_params=job_params)

        try:
            extra_headers, extra_body = self.openai_responses_factory.make_extras(
                inference_model=self.inference_model, inference_job=llm_job, output_desc=InferenceOutputType.TEXT
            )
            response = await self.openai_client_for_responses.responses.create(
                model=self.inference_model.model_id,
                instructions=llm_job.llm_prompt.system_text,
                temperature=omit if openai_reasoning is not None else job_params.temperature,
                max_output_tokens=job_params.max_tokens or omit,
                input=input_items,
                reasoning=openai_reasoning if openai_reasoning is not None else omit,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
        except (openai.APIStatusError, openai.APIConnectionError) as sdk_exc:
            metadata = extract_openai_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if not response.output_text:
            msg = f"OpenAI Responses message content is empty: {response}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="OpenAI Responses API returned no text — try rephrasing the prompt or using a different model",
                ),
            )

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and response.usage:
            llm_tokens_usage.nb_tokens_by_category = self.openai_responses_factory.make_nb_tokens_by_category(usage=response.usage)
        return response.output_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        self._validate_no_reasoning_for_structured_gen(job_params=job_params)
        from instructor.core import InstructorRetryException  # ruff: ignore[import-outside-top-level]

        if not hasattr(self.instructor_for_objects, "responses"):
            msg = "Instructor client is not configured for the Responses API. Set a responses-capable structure_method for this model."
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail=(
                        "The model's structure_method is not configured for the Responses API"
                        " — set a responses-capable structure_method or switch to a model that supports it"
                    ),
                ),
            )
        extra_headers, extra_body = self.openai_responses_factory.make_extras(
            inference_model=self.inference_model, inference_job=llm_job, output_desc=schema.__name__
        )
        input_items = await self.openai_responses_factory.make_input_items(llm_job=llm_job)
        try:
            result_object, completion = await self.instructor_for_objects.responses.create_with_completion(  # pyright: ignore[reportUnknownMemberType]
                input=cast("list[ChatCompletionMessageParam]", input_items),
                response_model=schema,
                # instructor's retry is confined to schema re-ask: this validation-only AsyncRetrying
                # re-asks on a malformed/invalid output but lets a transport error propagate as the raw
                # SDK exception — transport retry is the SDK client floor (Tier 1) alone.
                # The arg-type ignore below is because instructor's `responses` path is stub-typed
                # `int | Retrying`, but `initialize_retrying` accepts (and the async path needs) an `AsyncRetrying`.
                max_retries=make_instructor_schema_retrying(max_attempts=llm_job.job_config.schema_reask_max_attempts),  # type: ignore[arg-type]
                model=self.inference_model.model_id,
                instructions=llm_job.llm_prompt.system_text,
                temperature=job_params.temperature,
                max_output_tokens=job_params.max_tokens or NOT_GIVEN,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )  # type: ignore[arg-type,misc]
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth/not-found errors aren't flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if underlying_exc is not None:
                metadata = extract_openai_metadata(underlying_exc)
                classification = classify_inference_error(metadata)
                raise render_inference_error(
                    metadata=metadata,
                    classification=classification,
                    family=InferenceErrorFamily.LLM,
                    model_desc=self.inference_model.desc,
                    model_handle=self.inference_model.name,
                ) from instructor_exc
            msg = (
                f"OpenAI structured generation via 'instructor' failed with model: {self.inference_model.desc} "
                f"trying to generate schema: {schema} with error: {instructor_exc}"
            )
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.UNKNOWN) from instructor_exc
        except (openai.APIStatusError, openai.APIConnectionError) as sdk_exc:
            metadata = extract_openai_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and hasattr(completion, "usage"):
            completion_usage = completion.usage
            if completion_usage:
                llm_tokens_usage.nb_tokens_by_category = self.openai_responses_factory.make_nb_tokens_by_category(usage=completion_usage)

        typed_result_object: BaseModelTypeVar = result_object
        return typed_result_object
