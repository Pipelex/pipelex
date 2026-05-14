from typing import TYPE_CHECKING, Any

from mistralai import Mistral, MistralError
from mistralai.models import MistralPromptMode, TextChunk, ThinkChunk
from mistralai.types import UNSET
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCapabilityError, LLMCompletionError, SdkTypeError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_mistral_metadata,
    extract_underlying_sdk_exception,
    is_content_policy_violation,
    is_quota_exhaustion_mistral,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.mistral.mistral_exceptions import MistralWorkerConfigurationError
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.urls import URLs

if TYPE_CHECKING:
    from mistralai.models import ChatCompletionResponse
    from mistralai.types import OptionalNullable


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
        from instructor import from_mistral  # noqa: PLC0415

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_mistral(client=sdk_instance, mode=instructor_mode, use_async=True)
        else:
            self.instructor_for_objects = from_mistral(client=sdk_instance, use_async=True)

    def _classify_mistral_error(self, exc: MistralError) -> LLMCompletionError:
        """Classify a Mistral SDK error into a categorized LLMCompletionError.

        The returned error carries a structured ``provider_metadata`` and a
        semantic ``UserActionKind`` so downstream consumers (retry, CLI,
        telemetry) get uniform shape across providers.
        """
        error_message = str(exc)
        status_code = exc.status_code
        metadata = extract_mistral_metadata(exc)

        if is_quota_exhaustion_mistral(error_message, status_code):
            msg = f"Mistral quota exhausted for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your Mistral account has exceeded its quota — check billing at {URLs.mistral_billing}",
                ),
                provider_metadata=metadata,
            )

        if status_code in {401, 403}:
            msg = f"Mistral authentication error for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="Mistral rejected the API key — check your credentials",
                ),
                provider_metadata=metadata,
            )

        if status_code == 404:
            msg = f"Mistral model '{self.inference_model.desc}' not found: {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
                ),
                provider_metadata=metadata,
            )

        if status_code == 429:
            msg = f"Mistral rate limit exceeded for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Rate limited by Mistral — the system will retry automatically",
                ),
                provider_metadata=metadata,
            )

        if status_code == 400:
            if is_content_policy_violation(error_message):
                msg = f"Content rejected by safety filters for model '{self.inference_model.desc}': {exc}"
                return LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail="Content was rejected by safety filters — revise the prompt",
                    ),
                    provider_metadata=metadata,
                )
            msg = f"Mistral bad request error for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Mistral rejected the request — review the prompt and parameters",
                ),
                provider_metadata=metadata,
            )

        if status_code >= 500:
            msg = f"Mistral server error for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Mistral server error — the system will retry automatically",
                ),
                provider_metadata=metadata,
            )

        msg = f"Mistral API error for model '{self.inference_model.desc}': {exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Mistral API returned an unexpected error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    def _resolve_prompt_mode(self, job_params: LLMJobParams) -> "OptionalNullable[MistralPromptMode]":
        """Resolve reasoning parameters to a Mistral prompt_mode value.

        Args:
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.

        Returns:
            The Mistral prompt_mode value, or UNSET if reasoning is not requested.

        """
        thinking_mode = self.inference_model.thinking_mode

        if job_params.reasoning_budget is not None:
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    msg = f"Model '{self.inference_model.desc}' does not support reasoning_budget; Mistral uses prompt_mode instead"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{self.inference_model.desc}' has thinking_mode=adaptive which is not supported for Mistral models"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.NONE:
                    msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                    raise LLMCapabilityError(msg)

        if job_params.reasoning_effort is not None:
            effort = job_params.reasoning_effort
            match thinking_mode:
                case ThinkingMode.MANUAL:
                    prompt_mode = get_config().cogt.llm_config.mistral_config.get_reasoning_level(effort=effort)
                    if prompt_mode is None:
                        log.verbose("Mistral prompt_mode omitted (reasoning disabled)")
                        return UNSET
                    log.verbose(f"Mistral prompt_mode={prompt_mode}")
                    return prompt_mode
                case ThinkingMode.ADAPTIVE:
                    msg = f"Model '{self.inference_model.desc}' has thinking_mode=adaptive which is not supported for Mistral models"
                    raise LLMCapabilityError(msg)
                case ThinkingMode.NONE:
                    msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                    raise LLMCapabilityError(msg)

        return UNSET

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await self.mistral_factory.make_simple_messages(llm_job=llm_job)
        prompt_mode = self._resolve_prompt_mode(job_params=job_params)
        try:
            response: ChatCompletionResponse | None = await self.mistral_client_for_text.chat.complete_async(
                messages=messages,
                model=self.inference_model.model_id,
                temperature=job_params.temperature,
                max_tokens=job_params.max_tokens or self.default_max_tokens,
                prompt_mode=prompt_mode,
            )
        except MistralError as exc:
            raise self._classify_mistral_error(exc) from exc

        if not response:
            msg = "Mistral response is None"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Mistral returned an empty response — the system will retry automatically",
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
                    detail="Mistral returned a response with no choices — the system will retry automatically",
                ),
            )
        mistral_response_content = response.choices[0].message.content
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

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := response.usage):
            llm_tokens_usage.nb_tokens_by_category = self.mistral_factory.make_nb_tokens_by_category(usage=usage)

        return result_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        self._validate_no_reasoning_for_structured_gen(job_params=job_params)
        messages = await self.mistral_factory.make_simple_messages_openai_typed(llm_job=llm_job)
        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # noqa: PLC0415

        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                response_model=schema,
                messages=messages,
                model=self.inference_model.model_id,
                temperature=job_params.temperature,
                max_tokens=job_params.max_tokens or self.default_max_tokens,
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if isinstance(underlying_exc, MistralError):
                raise self._classify_mistral_error(underlying_exc) from instructor_exc
            msg = f"Mistral structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.UNKNOWN) from instructor_exc
        except MistralError as exc:
            raise self._classify_mistral_error(exc) from exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = self.mistral_factory.make_nb_tokens_by_category(usage=usage)

        return result_object
