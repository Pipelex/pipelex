from typing import TYPE_CHECKING, Any

from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
    omit,
)
from anthropic.types import OutputConfigParam, ThinkingConfigParam
from pydantic.dataclasses import dataclass as pydantic_dataclass
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCapabilityError, LLMCompletionError, SdkTypeError
from pipelex.cogt.inference.error_classification import (
    is_content_policy_violation,
    is_quota_exhaustion_anthropic,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_utils import (
    dump_error,
    dump_kwargs,
    dump_response_from_structured_gen,
)
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.anthropic.anthropic_exceptions import (
    AnthropicCredentialsError,
    AnthropicWorkerConfigurationError,
)
from pipelex.plugins.anthropic.anthropic_factory import (
    AnthropicFactory,
    AnthropicSdkVariant,
)
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.urls import URLs

if TYPE_CHECKING:
    from anthropic.types import Message


@pydantic_dataclass
class _ThinkingParams:
    """Container for thinking-related SDK parameters."""

    thinking: ThinkingConfigParam | None
    output_config: OutputConfigParam | None
    suppress_temperature: bool


class AnthropicLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
            self,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        self.extra_config: dict[str, Any] = extra_config
        self.default_max_tokens: int = 0
        if inference_model.max_tokens:
            self.default_max_tokens = inference_model.max_tokens
        else:
            msg = f"No max_tokens provided for llm model '{self.inference_model.desc}', but it is required for Anthropic"
            raise AnthropicWorkerConfigurationError(msg)

        # Verify if the sdk_instance is compatible with the current LLM platform
        if isinstance(sdk_instance, (AsyncAnthropic, AsyncAnthropicBedrock)):
            if (inference_model.sdk == AnthropicSdkVariant.ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropic))) or (
                inference_model.sdk == AnthropicSdkVariant.BEDROCK_ANTHROPIC and not (isinstance(sdk_instance, AsyncAnthropicBedrock))
            ):
                msg = f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}"
                raise SdkTypeError(msg)
        else:
            msg = f"Provided sdk_instance does not match LLMEngine platform:{sdk_instance}"
            raise SdkTypeError(msg)

        self.anthropic_async_client = sdk_instance
        from instructor import from_anthropic  # noqa: PLC0415

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_anthropic(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = from_anthropic(client=sdk_instance)

        instructor_config = get_config().cogt.llm_config.instructor_config
        if instructor_config.is_dump_kwargs_enabled:
            self.instructor_for_objects.on(hook_name="completion:kwargs", handler=dump_kwargs)
        if instructor_config.is_dump_response_enabled:
            self.instructor_for_objects.on(
                hook_name="completion:response",
                handler=dump_response_from_structured_gen,
            )
        if instructor_config.is_dump_error_enabled:
            self.instructor_for_objects.on(hook_name="completion:error", handler=dump_error)

    #########################################################
    # Instance methods
    #########################################################

    def _build_thinking_params(self, job_params: LLMJobParams, max_tokens: int) -> _ThinkingParams:
        """Build thinking-related SDK parameters from job params and model spec.

        Args:
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.
            max_tokens: The effective max_tokens for this request.

        Returns:
            A _ThinkingParams container with thinking, output_config, and suppress_temperature.

        """
        thinking_mode = self.inference_model.thinking_mode

        # Case 1: reasoning_effort is set
        if job_params.reasoning_effort is not None:
            effort = job_params.reasoning_effort
            return self._build_thinking_params_for_effort(thinking_mode=thinking_mode, effort=effort, max_tokens=max_tokens)

        # Case 2: reasoning_budget is set
        if job_params.reasoning_budget is not None:
            budget = job_params.reasoning_budget
            return self._build_thinking_params_for_budget(thinking_mode=thinking_mode, budget=budget, max_tokens=max_tokens)

        # Case 3: neither reasoning_effort nor reasoning_budget is set
        return _ThinkingParams(
            thinking=None,
            output_config=None,
            suppress_temperature=False,
        )

    def _build_thinking_params_for_effort(
        self,
        thinking_mode: ThinkingMode,
        effort: ReasoningEffort,
        max_tokens: int,
    ) -> _ThinkingParams:
        """Build thinking params when reasoning_effort is specified."""
        match thinking_mode:
            case ThinkingMode.ADAPTIVE:
                anthropic_effort = get_config().cogt.llm_config.anthropic_config.get_reasoning_level(effort=effort)
                if anthropic_effort is None:
                    # NONE effort means don't enable thinking at all
                    return _ThinkingParams(
                        thinking=None,
                        output_config=None,
                        suppress_temperature=False,
                    )
                log.verbose(f"Anthropic adaptive thinking with effort={anthropic_effort}")
                thinking_config: ThinkingConfigParam = {"type": "adaptive"}
                output_config = OutputConfigParam(effort=anthropic_effort)  # type: ignore[typeddict-item]  # pyright: ignore[reportArgumentType]
                return _ThinkingParams(
                    thinking=thinking_config,
                    output_config=output_config,
                    suppress_temperature=True,
                )
            case ThinkingMode.MANUAL:
                anthropic_effort = get_config().cogt.llm_config.anthropic_config.get_reasoning_level(effort=effort)
                if anthropic_effort is None:
                    # NONE effort means don't enable thinking
                    return _ThinkingParams(
                        thinking=None,
                        output_config=None,
                        suppress_temperature=False,
                    )
                prompting_target = self.inference_model.prompting_target
                if prompting_target is None:
                    msg = f"Model '{self.inference_model.desc}' has no prompting_target configured, cannot resolve reasoning budget"
                    raise LLMCapabilityError(msg)
                budget = get_config().cogt.llm_config.get_reasoning_budget(
                    prompting_target=prompting_target,
                    effort=effort,
                )
                safe_budget = min(budget, max_tokens - 1)
                log.verbose(f"Anthropic manual thinking with budget_tokens={safe_budget} (from effort={effort})")
                thinking_config = {"type": "enabled", "budget_tokens": safe_budget}
                return _ThinkingParams(
                    thinking=thinking_config,
                    output_config=None,
                    suppress_temperature=True,
                )
            case ThinkingMode.NONE:
                msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    def _build_thinking_params_for_budget(
        self,
        thinking_mode: ThinkingMode,
        budget: int,
        max_tokens: int,
    ) -> _ThinkingParams:
        """Build thinking params when reasoning_budget is specified."""
        match thinking_mode:
            case ThinkingMode.ADAPTIVE:
                msg = (
                    f"Model '{self.inference_model.desc}' uses adaptive thinking which does not support reasoning_budget. "
                    f"Use reasoning_effort instead (e.g. reasoning_effort='high')"
                )
                raise LLMCapabilityError(msg)
            case ThinkingMode.MANUAL:
                safe_budget = min(budget, max_tokens - 1)
                log.verbose(f"Anthropic thinking with explicit budget_tokens={safe_budget}")
                thinking_config: ThinkingConfigParam = {"type": "enabled", "budget_tokens": safe_budget}
                return _ThinkingParams(
                    thinking=thinking_config,
                    output_config=None,
                    suppress_temperature=True,
                )
            case ThinkingMode.NONE:
                msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    @staticmethod
    def _extract_underlying_sdk_exception(instructor_exc: Any) -> BaseException | None:
        """Recover the SDK exception that caused an ``InstructorRetryException``.

        instructor's retry loop wraps the last failed attempt's exception inside
        ``InstructorRetryException``. We prefer ``failed_attempts[-1].exception``
        (the documented public attribute) and fall back to walking ``__cause__``
        (a tenacity ``RetryError`` whose ``last_attempt._exception`` holds the
        original exception) when ``failed_attempts`` is unset.
        """
        failed_attempts = getattr(instructor_exc, "failed_attempts", None)
        if failed_attempts:
            last_exc = getattr(failed_attempts[-1], "exception", None)
            if isinstance(last_exc, BaseException):
                return last_exc
        cause = instructor_exc.__cause__
        last_attempt = getattr(cause, "last_attempt", None)
        if last_attempt is not None:
            underlying = getattr(last_attempt, "_exception", None)
            if isinstance(underlying, BaseException):
                return underlying
        return None

    def _raise_categorized_anthropic_sdk_error(
        self,
        sdk_exc: BaseException,
        chain_from: BaseException | None = None,
    ) -> None:
        """Categorize an Anthropic SDK exception and raise the matching pipelex error.

        Args:
            sdk_exc: The SDK exception to categorize. If it is not one of the
                recognized SDK exception types this method returns None and the
                caller is responsible for the fallback.
            chain_from: Override for ``raise ... from`` chaining (defaults to ``sdk_exc``).
                Used when the SDK exception was unwrapped from a wrapper (e.g.
                ``InstructorRetryException``) so the traceback preserves the wrapper.

        """
        cause = chain_from if chain_from is not None else sdk_exc

        if isinstance(sdk_exc, RateLimitError):
            error_message = str(sdk_exc)
            if is_quota_exhaustion_anthropic(error_message):
                msg = f"Anthropic quota exhausted for model '{self.inference_model.desc}': {sdk_exc}"
                raise LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.CAPACITY,
                    user_action=f"Your Anthropic account has exceeded its quota — check billing at {URLs.anthropic_billing}",
                ) from cause
            msg = f"Anthropic rate limit exceeded for model '{self.inference_model.desc}': {sdk_exc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action="Rate limited by Anthropic — the system will retry automatically",
            ) from cause

        if isinstance(sdk_exc, APITimeoutError):
            msg = f"Anthropic API request timed out for model '{self.inference_model.desc}': {sdk_exc}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.TRANSIENT) from cause

        if isinstance(sdk_exc, BadRequestError):
            error_message = str(sdk_exc)
            if is_content_policy_violation(error_message):
                msg = f"Content rejected by safety filters for model '{self.inference_model.desc}': {sdk_exc}"
                raise LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action="Content was rejected by safety filters — revise the prompt",
                ) from cause
            msg = f"Anthropic bad request error: {sdk_exc}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONTENT) from cause

        if isinstance(sdk_exc, APIConnectionError):
            msg = f"Anthropic API connection error: {sdk_exc}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.TRANSIENT) from cause

        if isinstance(sdk_exc, PermissionDeniedError):
            error_message = str(sdk_exc)
            if is_quota_exhaustion_anthropic(error_message):
                msg = f"Anthropic quota exhausted: {sdk_exc}"
                raise LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.CAPACITY,
                    user_action=f"Your Anthropic account has exceeded its quota — check billing at {URLs.anthropic_billing}",
                ) from cause
            msg = f"Anthropic permission denied: {sdk_exc}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONFIGURATION) from cause

        if isinstance(sdk_exc, AuthenticationError):
            msg = f"Anthropic credentials error: {sdk_exc}"
            raise AnthropicCredentialsError(msg) from cause

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        message = await AnthropicFactory.make_user_message(llm_job=llm_job)
        max_tokens = job_params.max_tokens or self.default_max_tokens

        thinking_params = self._build_thinking_params(job_params=job_params, max_tokens=max_tokens)
        log.verbose(thinking_params, title="Thinking params")
        log.verbose(max_tokens, title="Max tokens")

        try:
            # Use streaming internally to avoid SDK long-request protection
            temperature_unsupported = ListedConstraint.TEMPERATURE_UNSUPPORTED in self.inference_model.listed_constraints
            async with self.anthropic_async_client.messages.stream(
                messages=[message],
                system=llm_job.llm_prompt.system_text or omit,
                model=self.inference_model.model_id,
                temperature=omit if (thinking_params.suppress_temperature or temperature_unsupported) else job_params.temperature,
                max_tokens=max_tokens,
                thinking=thinking_params.thinking or omit,
                output_config=thinking_params.output_config or omit,
            ) as stream:
                final_message: Message = await stream.get_final_message()
        except (
            RateLimitError,
            APITimeoutError,
            BadRequestError,
            APIConnectionError,
            PermissionDeniedError,
            AuthenticationError,
        ) as sdk_exc:
            self._raise_categorized_anthropic_sdk_error(sdk_exc=sdk_exc)
            raise  # unreachable: helper always raises for these types

        # Collect all text blocks (adaptive thinking enables interleaved thinking,
        # so the response may contain multiple text blocks interspersed with thinking blocks)
        text_parts: list[str] = []
        block_types: list[str] = []
        for content_block in final_message.content:
            block_types.append(content_block.type)
            if content_block.type == "text":
                stripped = content_block.text.strip()
                if stripped:
                    text_parts.append(stripped)

        log.verbose(
            f"content_block_types={block_types}, text_parts_count={len(text_parts)}, "
            f"stop_reason={final_message.stop_reason}, usage={final_message.usage}",
            title="Anthropic response",
        )

        if not text_parts:
            msg = (
                f"No text content in response (model may have exhausted tokens on thinking)\n"
                f"model: {self.inference_model.desc}\nstop_reason: {final_message.stop_reason}\n"
                f"content_block_types: {block_types}"
            )
            raise LLMCompletionError(msg)

        full_reply_content = "\n\n".join(text_parts)

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and final_message.usage:
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=final_message.usage)

        return full_reply_content

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        self._validate_no_reasoning_for_structured_gen(job_params=job_params)
        messages = await AnthropicFactory.make_simple_messages(llm_job=llm_job)

        # Get Anthropic-specific config for structured output
        anthropic_config = get_config().cogt.llm_config.anthropic_config
        timeout_seconds = anthropic_config.structured_output_timeout_seconds

        # Calculate safe max_tokens based on timeout
        safe_max_tokens = AnthropicFactory.calculate_safe_max_tokens_for_timeout(timeout_seconds)

        # Use minimum of requested and safe limit
        requested_max_tokens = job_params.max_tokens or self.default_max_tokens
        effective_max_tokens = min(requested_max_tokens, safe_max_tokens)

        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # noqa: PLC0415

        temperature_unsupported = ListedConstraint.TEMPERATURE_UNSUPPORTED in self.inference_model.listed_constraints
        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                messages=messages,
                response_model=schema,
                max_retries=llm_job.job_config.max_retries,
                model=self.inference_model.model_id,
                temperature=omit if temperature_unsupported else job_params.temperature,
                max_tokens=effective_max_tokens,
                timeout=float(timeout_seconds),  # Explicit timeout disables SDK's long-request protection
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to CONTENT.
            underlying_exc = self._extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if underlying_exc is not None:
                self._raise_categorized_anthropic_sdk_error(sdk_exc=underlying_exc, chain_from=instructor_exc)
            msg = (
                f"Anthropic structured generation via 'instructor' failed with model: {self.inference_model.desc} "
                f"trying to generate schema: {schema} with error: {instructor_exc}"
            )
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONTENT) from instructor_exc
        except (
            RateLimitError,
            APITimeoutError,
            BadRequestError,
            APIConnectionError,
            PermissionDeniedError,
            AuthenticationError,
        ) as sdk_exc:
            self._raise_categorized_anthropic_sdk_error(sdk_exc=sdk_exc)
            raise  # unreachable: helper always raises for these types
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
