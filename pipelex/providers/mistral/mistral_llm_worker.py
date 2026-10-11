from typing import TYPE_CHECKING, Any

import httpx
from mistralai.client import Mistral
from mistralai.client.errors import MistralError
from mistralai.client.models import ReasoningEffort as MistralReasoningEffort
from mistralai.client.models import TextChunk, ThinkChunk
from mistralai.client.types import UNSET
from typing_extensions import override

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCapabilityError, LLMCompletionError, SdkTypeError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_mistral_metadata,
    extract_underlying_sdk_exception,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.providers.mistral.mistral_exceptions import MistralWorkerConfigurationError
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

if TYPE_CHECKING:
    from instructor import Mode as InstructorMode
    from mistralai.client.models import ChatCompletionResponse
    from mistralai.client.types import OptionalNullable


class MistralLLMWorker(LLMWorkerAbstract):
    def __init__(
        self,
        mistral_factory: MistralFactory,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerAbstract.__init__(
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
        from instructor import from_mistral  # ruff: ignore[import-outside-top-level]

        self.instructor_for_objects = from_mistral(client=sdk_instance, mode=self._instructor_mode(inference_model=inference_model), use_async=True)

    @classmethod
    @override
    def check_request(cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams, is_structured: bool) -> None:
        """Refuse a reasoning setting Mistral cannot carry for the model, and one on a structured output it cannot read back.

        A reasoning reply carries its answer beside a thinking chunk in a list of content chunks, which instructor's
        JSON parsers read as one string and refuse on every attempt; its tool mode reads the tool call and validates.
        So a structured output with a reasoning setting needs the tool structure method.
        """
        reasoning_effort = cls._resolve_reasoning_effort(inference_model=inference_model, job_params=job_params)
        if not is_structured or reasoning_effort is UNSET:
            return
        from instructor import Mode as InstructorMode  # ruff: ignore[import-outside-top-level]

        if cls._instructor_mode(inference_model=inference_model) != InstructorMode.TOOLS:
            msg = (
                f"Model '{inference_model.desc}' cannot reason on a structured output with structure method "
                f"'{inference_model.structure_method}': use 'instructor/mistral_tools', or remove the reasoning setting"
            )
            raise LLMCapabilityError(msg)

    @classmethod
    def _instructor_mode(cls, *, inference_model: InferenceModelSpec) -> "InstructorMode":
        """The instructor mode structured outputs use: the model's structure method's, else the tool mode."""
        from instructor import Mode as InstructorMode  # ruff: ignore[import-outside-top-level]

        return inference_model.get_instructor_mode() or InstructorMode.TOOLS

    @classmethod
    def _resolve_reasoning_effort(
        cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams
    ) -> "OptionalNullable[MistralReasoningEffort]":
        """Resolve reasoning parameters to a Mistral reasoning_effort value.

        Mistral's reasoning models take `reasoning_effort` and refuse the older `prompt_mode="reasoning"`.

        Args:
            inference_model: The spec of the model the request goes to.
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.

        Returns:
            The Mistral reasoning_effort value, or UNSET if reasoning is not requested.

        """
        thinking_mode = inference_model.thinking_mode

        if job_params.reasoning_budget is not None:
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    msg = f"Model '{inference_model.desc}' does not support reasoning_budget; Mistral uses reasoning_effort instead"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{inference_model.desc}' has thinking_mode=adaptive which is not supported for Mistral models"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.NONE:
                    msg = f"Model '{inference_model.desc}' does not support reasoning (thinking_mode=none)"
                    raise LLMCapabilityError(msg)

        if job_params.reasoning_effort is not None:
            effort = job_params.reasoning_effort
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    mistral_effort = get_config().inference.llm.mistral.get_reasoning_level(effort=effort)
                    return UNSET if mistral_effort is None else mistral_effort
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{inference_model.desc}' has thinking_mode=adaptive which is not supported for Mistral models"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.NONE:
                    msg = f"Model '{inference_model.desc}' does not support reasoning (thinking_mode=none)"
                    raise LLMCapabilityError(msg)

        return UNSET

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.mistral_factory.make_simple_messages(llm_job=llm_job)
        reasoning_effort = self._resolve_reasoning_effort(inference_model=self.inference_model, job_params=job_params)
        self._log_reasoning_sent(api_name="Mistral", settings={"reasoning_effort": None if reasoning_effort is UNSET else reasoning_effort})
        max_tokens = job_params.max_tokens or self.default_max_tokens
        try:
            response: ChatCompletionResponse | None = await self.mistral_client_for_text.chat.complete_async(
                messages=messages,
                model=self.inference_model.model_id,
                temperature=job_params.temperature if self.inference_model.accepts_temperature else UNSET,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        except (MistralError, httpx.TransportError) as sdk_exc:
            metadata = extract_mistral_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if not response:
            msg = "Mistral response is None"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Mistral returned an empty response — wait a moment, then run it again",
                ),
            )
        if not response.choices:
            msg = "Mistral response.choices is None"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Mistral returned a response with no choices — wait a moment, then run it again",
                ),
            )
        message = response.choices[0].message
        if message is None:
            msg = "Mistral response.choices[0].message is None"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Mistral returned a choice with no message — wait a moment, then run it again",
                ),
            )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = self.mistral_factory.make_nb_tokens_by_category(usage=usage)

        # Read before the content, so a text cut with nothing written is reported for what stopped it
        self._check_completion_stop(llm_job=llm_job, stop_reason=response.choices[0].finish_reason, max_tokens=max_tokens)

        mistral_response_content = message.content
        result_text: str
        if isinstance(mistral_response_content, str):
            result_text = mistral_response_content
        elif isinstance(mistral_response_content, list):
            # Reasoning models (magistral) return a list of chunks: ThinkChunk (reasoning trace) and TextChunk (answer)
            text_parts: list[str] = []
            for chunk in mistral_response_content:
                match chunk:
                    case TextChunk():
                        text_parts.append(chunk.text)
                    case ThinkChunk():
                        pass
                    case _:
                        pass
            result_text = "".join(text_parts)
        else:
            msg = f"Unexpected Mistral response content type: {type(mistral_response_content)}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="Mistral returned an unrecognized content type — report this to Pipelex support",
                ),
            )

        if not result_text:
            msg = "Mistral response text is empty"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Mistral returned an empty text response — try rephrasing the prompt or using a different model",
                ),
            )

        return result_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        reasoning_effort = self._resolve_reasoning_effort(inference_model=self.inference_model, job_params=job_params)
        self._log_reasoning_sent(api_name="Mistral", settings={"reasoning_effort": None if reasoning_effort is UNSET else reasoning_effort})
        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # ruff: ignore[import-outside-top-level]

        messages = await self.mistral_factory.make_simple_messages_openai_typed(llm_job=llm_job)

        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                response_model=schema,
                messages=messages,
                model=self.inference_model.model_id,
                temperature=job_params.temperature if self.inference_model.accepts_temperature else UNSET,
                max_tokens=job_params.max_tokens or self.default_max_tokens,
                reasoning_effort=reasoning_effort,
                # instructor's retry is confined to schema re-ask: this validation-only AsyncRetrying
                # re-asks on a malformed/invalid output but never retries a transport error, which ends the
                # loop and comes out wrapped, for the except clause below to unwrap — transport retry is the
                # SDK client floor (Tier 1) alone. Without this
                # the Mistral worker passed no max_retries at all, so structured Mistral got no re-ask.
                max_retries=make_instructor_schema_retrying(max_attempts=llm_job.job_config.schema_reask_max_attempts),
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if underlying_exc is not None:
                metadata = extract_mistral_metadata(underlying_exc)
                classification = classify_inference_error(metadata)
                raise render_inference_error(
                    metadata=metadata,
                    classification=classification,
                    family=InferenceErrorFamily.LLM,
                    model_desc=self.inference_model.desc,
                    model_handle=self.inference_model.name,
                ) from instructor_exc
            msg = f"Mistral structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="Structured generation failed for an unrecognized reason — retry, and report this if it persists",
                ),
            ) from instructor_exc
        except (MistralError, httpx.TransportError) as sdk_exc:
            metadata = extract_mistral_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = self.mistral_factory.make_nb_tokens_by_category(usage=usage)

        return result_object
