from typing import TYPE_CHECKING, Any, ClassVar

from anthropic import (
    APIConnectionError,
    APIStatusError,
    AsyncAnthropic,
    omit,
)
from anthropic.lib.bedrock import AsyncAnthropicBedrock
from anthropic.types import OutputConfigParam, ThinkingConfigParam
from pydantic.dataclasses import dataclass as pydantic_dataclass
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCapabilityError, LLMCompletionError, SdkTypeError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_anthropic_metadata,
    extract_underlying_sdk_exception,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_utils import (
    dump_error,
    dump_kwargs,
    dump_response_from_structured_gen,
)
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_budget import fit_thinking_budget
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.backend_extras_factory import BackendExtrasFactory
from pipelex.providers.anthropic.anthropic_exceptions import (
    AnthropicWorkerConfigurationError,
)
from pipelex.providers.anthropic.anthropic_factory import (
    AnthropicFactory,
    AnthropicSdkVariant,
)
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.telemetry.otel_constants import InferenceOutputType
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

if TYPE_CHECKING:
    from anthropic.types import Message


@pydantic_dataclass
class _ThinkingParams:
    """Container for thinking-related SDK parameters."""

    thinking: ThinkingConfigParam | None
    output_config: OutputConfigParam | None
    suppress_temperature: bool


class AnthropicLLMWorker(LLMWorkerAbstract):
    # Key into inference.llm.effort_to_budget_maps for manual-thinking budget resolution
    reasoning_budget_family: ClassVar[str] = "anthropic"

    def __init__(
        self,
        sdk_instance: Any,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
        extras_factory: BackendExtrasFactory | None = None,
    ):
        LLMWorkerAbstract.__init__(
            self,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        self.extra_config: dict[str, Any] = extra_config
        self.extras_factory = extras_factory
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
        from instructor import from_anthropic  # ruff: ignore[import-outside-top-level]

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_anthropic(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = from_anthropic(client=sdk_instance)

        instructor_config = get_config().inference.llm.instructor
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

    @classmethod
    @override
    def check_request(cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams, is_structured: bool) -> None:
        """Refuse a reasoning setting the model's thinking cannot take, or a thinking budget the call's max_tokens cannot hold."""
        requested_max_tokens = job_params.max_tokens or inference_model.max_tokens
        max_tokens = (
            None if requested_max_tokens is None else cls._sent_max_tokens(requested_max_tokens=requested_max_tokens, is_structured=is_structured)
        )
        cls._build_thinking_params(inference_model=inference_model, job_params=job_params, max_tokens=max_tokens)

    @classmethod
    def _sent_max_tokens(cls, *, requested_max_tokens: int, is_structured: bool) -> int:
        """The max_tokens a call sends: the one requested, capped on a structured output at what its timeout allows.

        A structured call sets an explicit timeout, which disables the SDK's long-request protection, so its
        max_tokens is held to what the SDK's own heuristic lets that timeout produce.
        """
        if not is_structured:
            return requested_max_tokens
        timeout_seconds = get_config().inference.llm.anthropic.structured_output_timeout_seconds
        safe_max_tokens = AnthropicFactory.calculate_safe_max_tokens_for_timeout(timeout_seconds=timeout_seconds)
        return min(requested_max_tokens, safe_max_tokens)

    def _say_max_tokens_lowered(
        self,
        *,
        is_caller_setting: bool,
        requested_max_tokens: int,
        effective_max_tokens: int,
        timeout_seconds: int,
    ) -> str | None:
        """Say that a structured call sends a lower max_tokens than it was given, and return the sentence its errors end with.

        A max_tokens the pipe's setting asked for and the call lowers is said at warning level, since the call then
        sends less than the method wrote. The model's own default lowered is said at debug level: a model whose
        default exceeds what the timeout allows has it lowered on every structured call, by design. Either way, an
        error the call raises says the limit was lowered and to what.

        Args:
            is_caller_setting: Whether the requested max_tokens is the pipe's setting rather than the model's default.
            requested_max_tokens: The max_tokens the call was given.
            effective_max_tokens: The max_tokens the call sends.
            timeout_seconds: The structured call's timeout, which the effective max_tokens fits.

        Returns:
            The sentence an error of the call ends with, None when the call sends the max_tokens it was given.
        """
        if effective_max_tokens >= requested_max_tokens:
            return None
        fields = {
            "model_handle": self.inference_model.name,
            "requested_max_tokens": requested_max_tokens,
            "effective_max_tokens": effective_max_tokens,
            "timeout_seconds": timeout_seconds,
        }
        if is_caller_setting:
            log.warning("A structured output's token limit was lowered to fit its timeout", fields=fields)
        else:
            log.debug("The model's default token limit was lowered to fit the structured output's timeout", fields=fields)
        return (
            f"The structured output's max_tokens was lowered from {requested_max_tokens} to {effective_max_tokens} "
            f"to fit its {timeout_seconds}-second timeout."
        )

    @classmethod
    def _with_note(cls, *, error: CogtError, note: str | None) -> CogtError:
        """The error a structured call raises, its message ending with the note when there is one.

        The note adds a fact to the error the call built and changes nothing else: its class, its category and
        whether it is retried stay what they were.
        """
        if note is None:
            return error
        error.message = f"{error.message} {note}"
        error.args = (error.message,)
        return error

    @classmethod
    def _build_thinking_params(cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams, max_tokens: int | None) -> _ThinkingParams:
        """Build thinking-related SDK parameters from job params and model spec.

        Args:
            inference_model: The spec of the model the request goes to.
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.
            max_tokens: The max_tokens this request sends, or None when no worker for the model can be built without one.

        Returns:
            A _ThinkingParams container with thinking, output_config, and suppress_temperature.

        """
        # Case 1: reasoning_effort is set
        if job_params.reasoning_effort is not None:
            effort = job_params.reasoning_effort
            return cls._build_thinking_params_for_effort(inference_model=inference_model, effort=effort, max_tokens=max_tokens)

        # Case 2: reasoning_budget is set
        if job_params.reasoning_budget is not None:
            budget = job_params.reasoning_budget
            return cls._build_thinking_params_for_budget(inference_model=inference_model, budget=budget, max_tokens=max_tokens)

        # Case 3: neither reasoning_effort nor reasoning_budget is set
        return _ThinkingParams(
            thinking=None,
            output_config=None,
            suppress_temperature=False,
        )

    @classmethod
    def _build_thinking_params_for_effort(
        cls,
        *,
        inference_model: InferenceModelSpec,
        effort: ReasoningEffort,
        max_tokens: int | None,
    ) -> _ThinkingParams:
        """Build thinking params when reasoning_effort is specified."""
        match inference_model.thinking_mode:
            case ThinkingMode.ADAPTIVE:
                anthropic_effort = get_config().inference.llm.anthropic.get_reasoning_level(effort=effort)
                if anthropic_effort is None:
                    # NONE effort means don't enable thinking at all
                    return _ThinkingParams(
                        thinking=None,
                        output_config=None,
                        suppress_temperature=False,
                    )
                thinking_config: ThinkingConfigParam = {"type": "adaptive"}
                output_config = OutputConfigParam(effort=anthropic_effort)  # type: ignore[typeddict-item]  # pyright: ignore[reportArgumentType]
                return _ThinkingParams(
                    thinking=thinking_config,
                    output_config=output_config,
                    suppress_temperature=True,
                )
            case ThinkingMode.MANUAL:
                anthropic_effort = get_config().inference.llm.anthropic.get_reasoning_level(effort=effort)
                if anthropic_effort is None:
                    # NONE effort means don't enable thinking
                    return _ThinkingParams(
                        thinking=None,
                        output_config=None,
                        suppress_temperature=False,
                    )
                budget = get_config().inference.llm.get_reasoning_budget(
                    family=cls.reasoning_budget_family,
                    effort=effort,
                )
                safe_budget = fit_thinking_budget(
                    budget=budget,
                    max_tokens=max_tokens,
                    min_budget=inference_model.min_thinking_budget,
                    max_budget=inference_model.max_thinking_budget,
                    model_desc=inference_model.desc,
                )
                thinking_config = {"type": "enabled", "budget_tokens": safe_budget}
                return _ThinkingParams(
                    thinking=thinking_config,
                    output_config=None,
                    suppress_temperature=True,
                )
            case ThinkingMode.NONE:
                msg = f"Model '{inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    @classmethod
    def _build_thinking_params_for_budget(
        cls,
        *,
        inference_model: InferenceModelSpec,
        budget: int,
        max_tokens: int | None,
    ) -> _ThinkingParams:
        """Build thinking params when reasoning_budget is specified."""
        match inference_model.thinking_mode:
            case ThinkingMode.ADAPTIVE:
                msg = (
                    f"Model '{inference_model.desc}' uses adaptive thinking which does not support reasoning_budget. "
                    f"Use reasoning_effort instead (e.g. reasoning_effort='high')"
                )
                raise LLMCapabilityError(msg)
            case ThinkingMode.MANUAL:
                safe_budget = fit_thinking_budget(
                    budget=budget,
                    max_tokens=max_tokens,
                    min_budget=inference_model.min_thinking_budget,
                    max_budget=inference_model.max_thinking_budget,
                    model_desc=inference_model.desc,
                )
                thinking_config: ThinkingConfigParam = {"type": "enabled", "budget_tokens": safe_budget}
                return _ThinkingParams(
                    thinking=thinking_config,
                    output_config=None,
                    suppress_temperature=True,
                )
            case ThinkingMode.NONE:
                msg = f"Model '{inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        message = await AnthropicFactory.make_user_message(llm_job=llm_job)
        max_tokens = self._sent_max_tokens(requested_max_tokens=job_params.max_tokens or self.default_max_tokens, is_structured=False)

        thinking_params = self._build_thinking_params(inference_model=self.inference_model, job_params=job_params, max_tokens=max_tokens)
        self._log_reasoning_sent(
            api_name="Anthropic", settings={"thinking": thinking_params.thinking, "output_config": thinking_params.output_config}
        )
        sends_temperature = self.inference_model.accepts_temperature and not thinking_params.suppress_temperature

        try:
            # Use streaming internally to avoid SDK long-request protection
            async with self.anthropic_async_client.messages.stream(
                messages=[message],
                system=llm_job.llm_prompt.system_text or omit,
                model=self.inference_model.model_id,
                temperature=job_params.temperature if sends_temperature else omit,
                max_tokens=max_tokens,
                thinking=thinking_params.thinking or omit,
                output_config=thinking_params.output_config or omit,
                **self._request_extras_kwargs(llm_job=llm_job, output_desc=InferenceOutputType.TEXT),
            ) as stream:
                final_message: Message = await stream.get_final_message()
        except (APIStatusError, APIConnectionError) as sdk_exc:
            metadata = extract_anthropic_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and final_message.usage:
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=final_message.usage)

        # Read before the text, so a text cut at max_tokens with nothing written, thinking having used the budget, is a truncation too
        self._check_completion_stop(llm_job=llm_job, stop_reason=final_message.stop_reason, max_tokens=max_tokens)

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

        if not text_parts:
            msg = (
                f"No text content in response (model may have exhausted tokens on thinking)\n"
                f"model: {self.inference_model.desc}\nstop_reason: {final_message.stop_reason}\n"
                f"content_block_types: {block_types}"
            )
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail=(
                        "Model produced no answer (likely exhausted token budget on reasoning)"
                        " — shorten the prompt, raise max_tokens, or disable thinking"
                    ),
                ),
            )

        return "\n\n".join(text_parts)

    def _request_extras_kwargs(self, *, llm_job: LLMJob, output_desc: str) -> dict[str, Any]:
        """The per-request headers and body additions this call sends, as SDK keyword arguments.

        None without an extras factory, which is every direct Anthropic and Bedrock path. A plugin that
        reaches a service of its own over the Anthropic protocol builds this worker with a
        `BackendExtrasFactory`, the same seam the OpenAI-substrate workers take, and its factory decides
        per request what joins the call: a header naming the job, for instance, where the credential is
        a client default.
        """
        if self.extras_factory is None:
            return {}
        extra_headers, extra_body = self.extras_factory.make_extras(self.inference_model, inference_job=llm_job, output_desc=output_desc)
        kwargs: dict[str, Any] = {}
        if extra_headers:
            kwargs["extra_headers"] = extra_headers
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def _structure_method_kwargs(self, *, thinking_params: _ThinkingParams) -> dict[str, Any]:
        """What the structured call sends, beyond what instructor's mode sets, for the model's structure method and thinking.

        instructor's tool mode forces `tool_choice` onto the response tool unless the request enables manual
        thinking, and Anthropic refuses a forced choice beside thinking. instructor does not recognise adaptive
        thinking, under which Anthropic accepts a forced choice and the model silently does not think. So whenever
        thinking is on, manual or adaptive, the request leaves `tool_choice` on auto with a system line steering the
        model to the tool call, the request instructor makes for manual thinking. A model that refuses a forced tool
        choice even without thinking, Fable 5.1 among them, names `anthropic_reasoning_tools` to get the same request
        always. instructor leaves a `tool_choice` it is given as it is, and sends a `system` it is given ahead of the
        prompt's. An auto choice would let the model answer with several tool calls, which instructor's parser
        refuses, so parallel tool use is disabled as instructor does on a forced choice. All of this concerns the
        tool modes only: a JSON mode defines no tool, and its request is left as instructor makes it.
        """
        from instructor import Mode as InstructorMode  # ruff: ignore[import-outside-top-level]

        if self.instructor_for_objects.mode != InstructorMode.TOOLS:
            return {}
        is_thinking = thinking_params.thinking is not None
        if not is_thinking and self.inference_model.structure_method != StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS:
            return {}
        return {
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "system": [{"type": "text", "text": "Return only the tool call and no additional text."}],
        }

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        job_params = llm_job.applied_job_params or llm_job.job_params
        messages = await AnthropicFactory.make_simple_messages(llm_job=llm_job)

        # The structured call sets an explicit timeout, and its max_tokens is held to what that timeout allows
        timeout_seconds = get_config().inference.llm.anthropic.structured_output_timeout_seconds
        requested_max_tokens = job_params.max_tokens or self.default_max_tokens
        effective_max_tokens = self._sent_max_tokens(requested_max_tokens=requested_max_tokens, is_structured=True)
        lowered_max_tokens_note = self._say_max_tokens_lowered(
            is_caller_setting=llm_job.job_params.max_tokens is not None,
            requested_max_tokens=requested_max_tokens,
            effective_max_tokens=effective_max_tokens,
            timeout_seconds=timeout_seconds,
        )

        # The thinking budget is fitted against the max_tokens this call actually sends
        thinking_params = self._build_thinking_params(inference_model=self.inference_model, job_params=job_params, max_tokens=effective_max_tokens)
        self._log_reasoning_sent(
            api_name="Anthropic", settings={"thinking": thinking_params.thinking, "output_config": thinking_params.output_config}
        )
        sends_temperature = self.inference_model.accepts_temperature and not thinking_params.suppress_temperature

        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # ruff: ignore[import-outside-top-level]

        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                messages=messages,
                response_model=schema,
                # instructor's retry is confined to schema re-ask: this validation-only AsyncRetrying
                # re-asks on a malformed/invalid output but never retries a transport error, which ends the
                # loop and comes out wrapped, for the except clause below to unwrap — transport retry is the
                # SDK client floor (Tier 1) alone.
                max_retries=make_instructor_schema_retrying(max_attempts=llm_job.job_config.schema_reask_max_attempts),
                model=self.inference_model.model_id,
                temperature=job_params.temperature if sends_temperature else omit,
                max_tokens=effective_max_tokens,
                thinking=thinking_params.thinking or omit,
                output_config=thinking_params.output_config or omit,
                timeout=float(timeout_seconds),  # Explicit timeout disables SDK's long-request protection
                **self._structure_method_kwargs(thinking_params=thinking_params),
                **self._request_extras_kwargs(llm_job=llm_job, output_desc=schema.__name__),
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if underlying_exc is not None:
                metadata = extract_anthropic_metadata(underlying_exc)
                classification = classify_inference_error(metadata)
                rendered_error = render_inference_error(
                    metadata=metadata,
                    classification=classification,
                    family=InferenceErrorFamily.LLM,
                    model_desc=self.inference_model.desc,
                    model_handle=self.inference_model.name,
                )
                raise self._with_note(error=rendered_error, note=lowered_max_tokens_note) from instructor_exc
            msg = (
                f"Anthropic structured generation via 'instructor' failed with model: {self.inference_model.desc} "
                f"trying to generate schema: {schema} with error: {instructor_exc}"
            )
            fallback_error = LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="Structured generation failed for an unrecognized reason — retry, and report this if it persists",
                ),
            )
            raise self._with_note(error=fallback_error, note=lowered_max_tokens_note) from instructor_exc
        except (APIStatusError, APIConnectionError) as sdk_exc:
            metadata = extract_anthropic_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            rendered_error = render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            )
            raise self._with_note(error=rendered_error, note=lowered_max_tokens_note) from sdk_exc
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and (usage := completion.usage):
            llm_tokens_usage.nb_tokens_by_category = AnthropicFactory.make_nb_tokens_by_category(usage=usage)

        return result_object
