import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

import httpx
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from google.genai.client import Client as GoogleGenAiClient
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCapabilityError, LLMCompletionError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_google_metadata,
    extract_underlying_sdk_exception,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_budget import fit_thinking_budget
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.providers.google.google_exceptions import GoogleLLMWorkerError
from pipelex.providers.google.google_factory import GoogleFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


class GoogleLLMWorker(LLMWorkerAbstract):
    # Key into inference.llm.effort_to_budget_maps for manual-thinking budget resolution
    reasoning_budget_family: ClassVar[str] = "gemini"

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
        from instructor import from_genai  # ruff: ignore[import-outside-top-level]

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = from_genai(client=sdk_instance, mode=instructor_mode, use_async=True)
        else:
            self.instructor_for_objects = from_genai(client=sdk_instance, use_async=True)

        instructor_config = get_config().inference.llm.instructor
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
                task.add_done_callback(lambda done: GoogleFactory.log_client_close_failure(close_task=done))
                return

            # Otherwise, try to get the current running loop
            try:
                current_loop = asyncio.get_running_loop()
                # Schedule cleanup on the current running loop and store reference to prevent garbage collection
                task = current_loop.create_task(self.genai_async_client.aclose())
                # Add a callback to log any errors that occur during cleanup
                task.add_done_callback(lambda done: GoogleFactory.log_client_close_failure(close_task=done))
            except RuntimeError:
                # No running event loop, we can safely use asyncio.run()
                try:
                    asyncio.run(self.genai_async_client.aclose())
                except Exception as exc:  # ruff: ignore[blind-except]
                    # Best-effort: asyncio.run() runs aclose(), whose failure surface is not enumerable; teardown must never fail.
                    log.debug("A Google async client could not be closed", fields=error_fields(exc=exc))
        except Exception as exc:  # ruff: ignore[blind-except]
            # Best-effort cleanup boundary: teardown must never fail, whatever client/event-loop close throws.
            log.debug("A Google async client could not be closed", fields=error_fields(exc=exc))

    #########################################################
    # Reasoning helpers
    #########################################################

    @classmethod
    @override
    def check_request(cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams, is_structured: bool) -> None:
        """Refuse a reasoning setting the model's thinking cannot take, or a thinking budget the call's max_tokens cannot hold."""
        cls._build_thinking_config(inference_model=inference_model, job_params=job_params, max_tokens=job_params.max_tokens)

    @classmethod
    def _build_thinking_config(
        cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams, max_tokens: int | None
    ) -> genai_types.ThinkingConfig | None:
        """Build thinking config from job params and model spec.

        Args:
            inference_model: The spec of the model the request goes to.
            job_params: The LLM job parameters containing reasoning_effort/reasoning_budget.
            max_tokens: The effective max_tokens for this request, used to cap the thinking budget.

        Returns:
            A ThinkingConfig for the Google GenAI SDK, or None if reasoning is not requested.

        """
        # Case 1: reasoning_effort is set
        if job_params.reasoning_effort is not None:
            return cls._build_thinking_config_for_effort(inference_model=inference_model, effort=job_params.reasoning_effort, max_tokens=max_tokens)

        # Case 2: reasoning_budget is set
        if job_params.reasoning_budget is not None:
            return cls._build_thinking_config_for_budget(inference_model=inference_model, budget=job_params.reasoning_budget, max_tokens=max_tokens)

        # Case 3: neither reasoning_effort nor reasoning_budget is set
        return None

    @classmethod
    def _build_thinking_config_for_effort(
        cls,
        *,
        inference_model: InferenceModelSpec,
        effort: ReasoningEffort,
        max_tokens: int | None,
    ) -> genai_types.ThinkingConfig:
        """Build thinking config when reasoning_effort is specified."""
        match inference_model.thinking_mode:
            case ThinkingMode.MANUAL:
                google_level = get_config().inference.llm.google.get_reasoning_level(effort=effort)
                if google_level is None:
                    return cls._thinking_off_config(inference_model=inference_model)
                budget = get_config().inference.llm.get_reasoning_budget(
                    family=cls.reasoning_budget_family,
                    effort=effort,
                )
                budget = fit_thinking_budget(
                    budget=budget,
                    max_tokens=max_tokens,
                    min_budget=inference_model.min_thinking_budget,
                    max_budget=inference_model.max_thinking_budget,
                    model_desc=inference_model.desc,
                )
                return genai_types.ThinkingConfig(thinking_budget=budget)
            case ThinkingMode.ADAPTIVE:
                thinking_level = get_config().inference.llm.google.get_reasoning_level(effort=effort)
                if thinking_level is None:
                    return cls._thinking_off_config(inference_model=inference_model)
                return genai_types.ThinkingConfig(thinking_level=thinking_level)
            case ThinkingMode.NONE:
                msg = f"Model '{inference_model.desc}' does not support reasoning (thinking_mode=none)"
                raise LLMCapabilityError(msg)

    @classmethod
    def _thinking_off_config(cls, *, inference_model: InferenceModelSpec) -> genai_types.ThinkingConfig:
        """Build the thinking config that turns thinking off, which a model that always thinks refuses with a 400."""
        if ListedConstraint.THINKING_CANNOT_BE_DISABLED in inference_model.listed_constraints:
            msg = (
                f"Model '{inference_model.desc}' cannot turn thinking off, so it cannot take reasoning_effort 'none': "
                f"set another reasoning effort, or remove the reasoning setting"
            )
            raise LLMCapabilityError(msg)
        return genai_types.ThinkingConfig(thinking_budget=0)

    @classmethod
    def _thinking_settings_sent(cls, *, thinking_config: genai_types.ThinkingConfig | None) -> dict[str, Any]:
        """The thinking settings as the request sends them: the wire values, `HIGH` rather than the SDK's `ThinkingLevel` member."""
        if thinking_config is None:
            return {}
        return thinking_config.model_dump(mode="json", exclude_none=True)

    @classmethod
    def _build_thinking_config_for_budget(
        cls,
        *,
        inference_model: InferenceModelSpec,
        budget: int,
        max_tokens: int | None,
    ) -> genai_types.ThinkingConfig:
        """Build thinking config when reasoning_budget is specified."""
        match inference_model.thinking_mode:
            case ThinkingMode.MANUAL | ThinkingMode.ADAPTIVE:
                budget = fit_thinking_budget(
                    budget=budget,
                    max_tokens=max_tokens,
                    min_budget=inference_model.min_thinking_budget,
                    max_budget=inference_model.max_thinking_budget,
                    model_desc=inference_model.desc,
                )
                return genai_types.ThinkingConfig(thinking_budget=budget)
            case ThinkingMode.NONE:
                msg = f"Model '{inference_model.desc}' does not support reasoning (thinking_mode=none)"
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

        thinking_config = self._build_thinking_config(inference_model=self.inference_model, job_params=job_params, max_tokens=job_params.max_tokens)
        self._log_reasoning_sent(api_name="Google", settings=self._thinking_settings_sent(thinking_config=thinking_config))

        # Build generation config
        generation_config = genai_types.GenerateContentConfig(
            temperature=job_params.temperature if self.inference_model.accepts_temperature else None,
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
        except (genai_errors.ServerError, genai_errors.ClientError, httpx.TransportError) as sdk_exc:
            metadata = extract_google_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        # Extract text from response (skips thinking parts)
        text_content = GoogleFactory.extract_text_from_response(response=response, model_desc=self.inference_model.desc)

        # Track token usage if available
        if llm_job.job_report.llm_tokens_usage and response.usage_metadata:
            llm_job.job_report.llm_tokens_usage.nb_tokens_by_category = GoogleFactory.extract_token_usage(response.usage_metadata)

        return text_content

    def _validates_structured_output_strictly(self) -> bool:
        """Whether ``instructor`` validates a structured response in pydantic's strict mode.

        Under tool calling, Gemini's function-call arguments reach ``instructor`` as Python values, and strict
        mode refuses a string for an enum field when it validates Python input, so every schema with an enum
        would fail. Gemini's native JSON output is parsed from text, where strict mode accepts a string for an
        enum. So tool calling validates in lax mode, and JSON output stays strict.
        """
        from instructor import Mode as InstructorMode  # ruff: ignore[import-outside-top-level]

        match self.instructor_for_objects.mode:
            case InstructorMode.TOOLS:
                return False
            case _:
                # `from_genai` supports only TOOLS and JSON; any other mode is parsed from text like JSON.
                return True

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        """Generate structured output using Google Gemini API with instructor."""
        job_params = llm_job.applied_job_params or llm_job.job_params
        thinking_config = self._build_thinking_config(inference_model=self.inference_model, job_params=job_params, max_tokens=job_params.max_tokens)
        self._log_reasoning_sent(api_name="Google", settings=self._thinking_settings_sent(thinking_config=thinking_config))
        # instructor's genai handlers read the system prompt only from `system`, and pop it only when it is not
        # None: a `system=None` reaches `generate_content`, which refuses the unknown keyword
        system_kwargs: dict[str, Any] = {"system": system_text} if (system_text := llm_job.llm_prompt.system_text) else {}
        contents = await GoogleFactory.prepare_user_contents(llm_job.llm_prompt)

        # Deferred import: avoid pulling heavy SDK at module-load time
        from instructor.core import InstructorRetryException  # ruff: ignore[import-outside-top-level]

        try:
            result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
                messages=[cast("ChatCompletionMessageParam", contents)],
                response_model=schema,
                # instructor's retry is confined to schema re-ask: this validation-only AsyncRetrying
                # re-asks on a malformed/invalid output but never retries a transport error, which ends the
                # loop and comes out wrapped, for the except clause below to unwrap — transport retry is the
                # SDK client floor (Tier 1) alone.
                max_retries=make_instructor_schema_retrying(max_attempts=llm_job.job_config.schema_reask_max_attempts),
                model=self.inference_model.model_id,
                # instructor's genai handlers build the Google config themselves and read these as
                # top-level OpenAI-style kwargs: a `GenerateContentConfig` passed as `generation_config`
                # or `config` is dropped.
                **system_kwargs,
                # None sets no temperature in the config the handlers build
                temperature=job_params.temperature if self.inference_model.accepts_temperature else None,
                max_tokens=job_params.max_tokens,
                n=1,
                strict=self._validates_structured_output_strictly(),
                # Read into the config the handlers build, as the other kwargs above; None sets no thinking config
                thinking_config=thinking_config,
            )
        except InstructorRetryException as instructor_exc:
            # instructor wraps SDK exceptions during retries; recover the underlying
            # one so transient/capacity/auth errors aren't all flattened to UNKNOWN.
            underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
            if underlying_exc is not None:
                metadata = extract_google_metadata(underlying_exc)
                classification = classify_inference_error(metadata)
                raise render_inference_error(
                    metadata=metadata,
                    classification=classification,
                    family=InferenceErrorFamily.LLM,
                    model_desc=self.inference_model.desc,
                    model_handle=self.inference_model.name,
                ) from instructor_exc
            msg = f"Google structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="Structured generation failed for an unrecognized reason — retry, and report this if it persists",
                ),
            ) from instructor_exc
        except (genai_errors.ServerError, genai_errors.ClientError, httpx.TransportError) as sdk_exc:
            metadata = extract_google_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

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
