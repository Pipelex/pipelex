import asyncio
from typing import TYPE_CHECKING, cast

import instructor
from google import genai
from google.genai import types as genai_types
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_utils import dump_error, dump_kwargs, dump_response_from_structured_gen
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.plugins.google.google_factory import GoogleFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


class GoogleLLMWorkerError(PipelexError):
    """Base exception for Google LLM Worker errors."""


class GoogleLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: genai.Client,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        genai_client: genai.Client = sdk_instance
        self.genai_async_client = genai_client.aio

        if instructor_mode := self.inference_model.get_instructor_mode():
            self.instructor_for_objects = instructor.from_genai(client=sdk_instance, mode=instructor_mode, use_async=True)
        else:
            self.instructor_for_objects = instructor.from_genai(client=sdk_instance, use_async=True)

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

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        """Generate text using Google Gemini API."""
        job_params = llm_job.applied_job_params or llm_job.job_params

        contents = await GoogleFactory.prepare_user_contents(llm_prompt=llm_job.llm_prompt)

        # Build generation config
        generation_config = genai_types.GenerateContentConfig(
            temperature=job_params.temperature,
            max_output_tokens=job_params.max_tokens,
            candidate_count=1,  # Generate one candidate
        )

        # Add system instruction if present (as part of config)
        if llm_job.llm_prompt.system_text:
            generation_config.system_instruction = llm_job.llm_prompt.system_text

        # Generate content using async client
        response = await self.genai_async_client.models.generate_content(
            model=self.inference_model.model_id,
            contents=contents,
            config=generation_config,
        )

        # Extract text from response
        if not response.candidates:
            msg = f"No candidates returned from model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            msg = f"No content parts in response from model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        # Extract text from the first part
        text_content = candidate.content.parts[0].text
        if not text_content:
            msg = f"No text content in response from model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

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
        contents = await GoogleFactory.prepare_user_contents(llm_job.llm_prompt)

        # Build generation config
        generation_config = genai_types.GenerateContentConfig(
            system_instruction=llm_job.llm_prompt.system_text,
            temperature=job_params.temperature,
            max_output_tokens=job_params.max_tokens,
            candidate_count=1,
        )

        result_object, completion = await self.instructor_for_objects.chat.completions.create_with_completion(
            messages=[cast("ChatCompletionMessageParam", contents)],
            response_model=schema,
            max_retries=llm_job.job_config.max_retries,
            model=self.inference_model.model_id,
            generation_config=generation_config,
        )
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
