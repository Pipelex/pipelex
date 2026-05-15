import asyncio
from typing import TYPE_CHECKING, cast

from google.genai import errors as genai_errors
from google.genai import types as genai_types
from google.genai.client import Client as GoogleGenAiClient
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCapabilityError, LLMCompletionError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_google_metadata,
    extract_underlying_sdk_exception,
    is_content_policy_violation,
    is_quota_exhaustion_google,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.plugins.google.google_factory import GoogleFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.urls import URLs

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


class GoogleLLMWorkerError(PipelexError):
    """Base exception for Google LLM Worker errors."""


class GoogleLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: GoogleGenAiClient,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        genai_client: GoogleGenAiClient = sdk_instance
        self.genai_async_client = genai_client.aio
        from instructor import from_genai  # noqa: PLC0415

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_genai(client=sdk_instance, mode=instructor_mode, use_async=True)
        else:
            self.instructor_for_objects = from_genai(client=sdk_instance, use_async=True)

        instructor_config = get_config().cogt.llm_config.instructor_config
        if instructor_config.is_dump_kwargs_enabled:
            self.instructor_for_objects.on(hook_name="completion:kwargs", handler=dump_kwargs)
        if instructor_config.is_dump_response_enabled:
            self.instructor_for_objects.on(hook_name="completion:response", handler=dump_response_from_structured_gen)
        if instructor_config.is_dump_error_enabled:
            self.instructor_for_objects.on(hook_name="completion:error", handler=dump_error)

        # Capture the event loop at creation time if one is running
        self._event_loop: asyncio.AbstractEventLoop | None
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop at creation time
            self._event_loop = None

    @override
    def teardown(self):
        """Close the async client to free resources."""
        try:
            # First, try to use the loop captured at creation time if it's still running
            if self._event_loop is not None and self._event_loop.is_running():
                # Schedule cleanup on the captured loop and store reference to prevent garbage collection
                task = self._event_loop.create_task(self.genai_async_client.aclose())
                # Add a callback to log any errors that occur during cleanup
                task.add_done_callback(lambda t: log.debug(f"Google async client cleanup error: {t.exception()}") if t.exception() else None)
                log.verbose("Scheduled Google async client cleanup on captured event loop")
                return

            # Otherwise, try to get the current running loop
            try:
                current_loop = asyncio.get_running_loop()
                # Schedule cleanup on the current running loop and store reference to prevent garbage collection
                task = current_loop.create_task(self.genai_async_client.aclose())
                # Add a callback to log any errors that occur during cleanup
                task.add_done_callback(lambda t: log.debug(f"Google async client cleanup error: {t.exception()}") if t.exception() else None)
                log.verbose("Scheduled Google async client cleanup on current event loop")
            except RuntimeError:
                # No running event loop, we can safely use asyncio.run()
                try:
                    asyncio.run(self.genai_async_client.aclose())
                    log.verbose("Closed Google async client using asyncio.run()")
                except Exception as exc:
                    # Log but don't fail teardown if cleanup has issues
                    log.verbose(f"Error closing Google async client during teardown: {exc}")
        except Exception as exc:
            # Log but don't fail teardown if cleanup has issues
            log.debug(f"Error during Google async client teardown: {exc}")

    #########################################################
    # Error classification
    #########################################################

    def _classify_google_client_error(self, exc: genai_errors.ClientError) -> LLMCompletionError:
        """Classify a Google GenAI ClientError into a categorized LLMCompletionError.

        The returned error carries a structured ``provider_metadata`` and a
        semantic ``UserActionKind`` so downstream consumers (retry, CLI,
        telemetry) get uniform shape across providers.
        """
        error_message = str(exc)
        status_code = exc.code
        metadata = extract_google_metadata(exc)

        if status_code == 404:
            msg = f"Google model '{self.inference_model.desc}' not found: {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
                ),
                provider_metadata=metadata,
            )

        if status_code in {401, 403}:
            msg = f"Google API permission denied for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="Google rejected the API credentials — check your project, API key, and IAM permissions",
                ),
                provider_metadata=metadata,
            )

        if status_code == 429:
            if is_quota_exhaustion_google(error_message):
                msg = f"Google quota exhausted for model '{self.inference_model.desc}': {exc}"
                return LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.CAPACITY,
                    user_action=UserAction(
                        kind=UserActionKind.CHECK_BILLING,
                        detail=f"Your Google Cloud account has exceeded its quota — check billing at {URLs.google_billing}",
                    ),
                    provider_metadata=metadata,
                )
            msg = f"Google rate limit exceeded for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Rate limited by Google — the system will retry automatically",
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
            msg = f"Google bad request error for model '{self.inference_model.desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Google rejected the request — review the prompt and parameters",
                ),
                provider_metadata=metadata,
            )

        # Fallback for other 4xx errors: a ClientError is always 4xx, so it is a
        # non-retryable client-side problem — not a transient one.
        msg = f"Google API client error for model '{self.inference_model.desc}': {exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Google rejected the request — review the prompt, parameters, and model configuration",
            ),
            provider_metadata=metadata,
        )

    def _raise_categorized_google_sdk_error(
        self,
        sdk_exc: BaseException,
        chain_from: BaseException | None = None,
    ) -> None:
        """Raise an ``LLMCompletionError`` categorized from a Google SDK exception.

        Used by both the direct path (where ``chain_from`` defaults to
        ``sdk_exc``) and the wrapped path (where ``chain_from`` is the
        ``InstructorRetryException``). ``ServerError`` is handled directly here
        — it doesn't need the 4xx discriminator in
        ``_classify_google_client_error``.

        Args:
            sdk_exc: The Google SDK exception to categorize.
            chain_from: Override for ``raise ... from`` chaining (defaults to ``sdk_exc``).
        """
        cause = chain_from if chain_from is not None else sdk_exc
        if isinstance(sdk_exc, genai_errors.ServerError):
            msg = f"Google API server error for model '{self.inference_model.desc}': {sdk_exc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Google API server error — the system will retry automatically",
                ),
                provider_metadata=extract_google_metadata(sdk_exc),
            ) from cause
        if isinstance(sdk_exc, genai_errors.ClientError):
            raise self._classify_google_client_error(sdk_exc) from cause

    #########################################################
    # Reasoning helpers
    #########################################################

    def _build_thinking_config(self, job_params: LLMJobParams, max_tokens: int | None) -> genai_types.ThinkingConfig | None:
        """Build thinking config from job params and model spec.

        Args:
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.
            max_tokens: The effective max_tokens for this request, used to cap the thinking budget.

        Returns:
            A ThinkingConfig for the Google GenAI SDK, or None if reasoning is not requested.

        """
        thinking_mode = self.inference_model.thinking_mode

        # Case 1: reasoning_effort is set
        if job_params.reasoning_effort is not None:
            return self._build_thinking_config_for_effort(thinking_mode=thinking_mode, effort=job_params.reasoning_effort, max_tokens=max_tokens)

        # Case 2: reasoning_budget is set
        if job_params.reasoning_budget is not None:
            return self._build_thinking_config_for_budget(thinking_mode=thinking_mode, budget=job_params.reasoning_budget, max_tokens=max_tokens)

        # Case 3: neither reasoning_effort nor reasoning_budget is set
        return None

    def _build_thinking_config_for_effort(
        self,
        thinking_mode: ThinkingMode,
        effort: ReasoningEffort,
        max_tokens: int | None,
    ) -> genai_types.ThinkingConfig:
        """Build thinking config when reasoning_effort is specified."""
        match thinking_mode:
            case ThinkingMode.MANUAL:
                google_level = get_config().cogt.llm_config.google_config.get_reasoning_level(effort=effort)
                if google_level is None:
                    log.verbose("Google manual thinking disabled (effort mapped to disabled)")
                    return genai_types.ThinkingConfig(thinking_budget=0)
                prompting_target = self.inference_model.prompting_target
                if prompting_target is None:
                    msg = f"Model '{self.inference_model.desc}' has no prompting_target configured, cannot resolve reasoning budget"
                    raise LLMCapabilityError(msg)
                budget = get_config().cogt.llm_config.get_reasoning_budget(
                    prompting_target=prompting_target,
                    effort=effort,
                )
                if max_tokens is not None:
                    budget = min(budget, max_tokens - 1)
                log.verbose(f"Google manual thinking with thinking_budget={budget} (from effort={effort})")
                return genai_types.ThinkingConfig(thinking_budget=budget)
            case ThinkingMode.ADAPTIVE:
                thinking_level = get_config().cogt.llm_config.google_config.get_reasoning_level(effort=effort)
                if thinking_level is None:
                    log.verbose("Google adaptive thinking disabled (effort=NONE)")
                    return genai_types.ThinkingConfig(thinking_budget=0)
                log.verbose(f"Google adaptive thinking with thinking_level={thinking_level}")
                return genai_types.ThinkingConfig(thinking_level=thinking_level)
            case ThinkingMode.NONE:
                msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    def _build_thinking_config_for_budget(
        self,
        thinking_mode: ThinkingMode,
        budget: int,
        max_tokens: int | None,
    ) -> genai_types.ThinkingConfig:
        """Build thinking config when reasoning_budget is specified."""
        match thinking_mode:
            case ThinkingMode.MANUAL | ThinkingMode.ADAPTIVE:
                if max_tokens is not None:
                    budget = min(budget, max_tokens - 1)
                log.verbose(f"Google thinking with explicit thinking_budget={budget}")
                return genai_types.ThinkingConfig(thinking_budget=budget)
            case ThinkingMode.NONE:
                msg = f"Model '{self.inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    #########################################################

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        """Generate text using Google Gemini API."""
        job_params = llm_job.applied_job_params or llm_job.job_params

        contents = await GoogleFactory.prepare_user_contents(llm_prompt=llm_job.llm_prompt)

        thinking_config = self._build_thinking_config(job_params=job_params, max_tokens=job_params.max_tokens)

        # Build generation config
        generation_config = genai_types.GenerateContentConfig(
            temperature=job_params.temperature,
            max_output_tokens=job_params.max_tokens,
            candidate_count=1,  # Generate one candidate
            thinking_config=thinking_config,
        )

        # Add system instruction if present (as part of config)
        if llm_job.llm_prompt.system_text:
            generation_config.system_instruction = llm_job.llm_prompt.system_text

        # Generate content using async client
        try:
            response = await self.genai_async_client.models.generate_content(
                model=self.inference_model.model_id,
                contents=contents,
                config=generation_config,
            )
        except (genai_errors.ServerError, genai_errors.ClientError) as exc:
            self._raise_categorized_google_sdk_error(sdk_exc=exc)
            raise  # unreachable: helper always raises for these types

        # Extract text from response (skips thinking parts)
        text_content = GoogleFactory.extract_text_from_response(response=response, model_desc=self.inference_model.desc)

        # Track token usage if available
        if llm_job.job_report.llm_tokens_usage and response.usage_metadata:
            llm_job.job_report.llm_tokens_usage.nb_tokens_by_category = GoogleFactory.extract_token_usage(response.usage_metadata)

        return text_content

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        """Generate structured output using Google Gemini API with instructor."""
        job_params = llm_job.applied_job_params or llm_job.job_params
        self._validate_no_reasoning_for_structured_gen(job_params=job_params)
        contents = await GoogleFactory.prepare_user_contents(llm_job.llm_prompt)

        # Build generation config
        generation_config = genai_types.GenerateContentConfig(
            system_instruction=llm_job.llm_prompt.system_text,
            temperature=job_params.temperature,
            max_output_tokens=job_params.max_tokens,
            candidate_count=1,
        )

        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # noqa: PLC0415

        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                messages=[cast("ChatCompletionMessageParam", contents)],
                response_model=schema,
                max_retries=llm_job.job_config.max_retries,
                model=self.inference_model.model_id,
                generation_config=generation_config,
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if isinstance(underlying_exc, (genai_errors.ServerError, genai_errors.ClientError)):
                self._raise_categorized_google_sdk_error(sdk_exc=underlying_exc, chain_from=instructor_exc)
            msg = f"Google structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.UNKNOWN) from instructor_exc
        except (genai_errors.ServerError, genai_errors.ClientError) as exc:
            self._raise_categorized_google_sdk_error(sdk_exc=exc)
            raise  # unreachable: helper always raises for these types

        if not isinstance(result_object, schema):
            msg = f"Google Gemini API returned an object that is not of type {schema}: {result_object}"
            raise GoogleLLMWorkerError(msg)

        # Track token usage if available from completion
        if llm_job.job_report.llm_tokens_usage:
            # Instructor may provide usage information in the completion object
            if hasattr(completion, "usage_metadata"):
                llm_job.job_report.llm_tokens_usage.nb_tokens_by_category = GoogleFactory.extract_token_usage(completion.usage_metadata)
            elif hasattr(completion, "usage"):
                # Fallback to standard usage format
                usage = completion.usage
                nb_tokens: NbTokensByCategoryDict = {}
                if hasattr(usage, "prompt_tokens"):
                    nb_tokens[TokenCategory.INPUT] = usage.prompt_tokens
                if hasattr(usage, "completion_tokens"):
                    nb_tokens[TokenCategory.OUTPUT] = usage.completion_tokens
                llm_job.job_report.llm_tokens_usage.nb_tokens_by_category = nb_tokens

        return result_object
