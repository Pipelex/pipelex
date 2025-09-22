from typing import Any, List, Optional, Type, Union

import instructor
from google import genai
from google.genai import types
from instructor.mode import Mode as InstructorMode
from typing_extensions import override

from pipelex import log
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class GoogleLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: genai.Client,
        inference_model: InferenceModelSpec,
        structure_method: Optional[StructureMethod] = None,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        super().__init__(
            inference_model=inference_model,
            structure_method=structure_method,
            reporting_delegate=reporting_delegate,
        )
        self.client: genai.Client = sdk_instance
        if structure_method:
            instructor_mode = structure_method.as_instructor_mode()
            log.debug(f"Google structure mode: {structure_method} --> {instructor_mode}")
            self.instructor_for_objects = instructor.from_genai(client=sdk_instance, mode=instructor_mode)
        else:
            self.instructor_for_objects = instructor.from_genai(client=sdk_instance)

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        """Generate text using Google Gemini API."""
        contents = self._prepare_contents(llm_job.llm_prompt)

        # Use the async client
        aclient = self.client.aio

        # Get temperature and max_tokens from job_params
        temperature = llm_job.job_params.temperature
        max_tokens = llm_job.job_params.max_tokens

        config = types.GenerateContentConfig(
            temperature=float(temperature),
            max_output_tokens=max_tokens if max_tokens is not None else None,
        )

        response = await aclient.models.generate_content(
            model=self.inference_model.model_id,
            contents=contents,
            config=config,
        )

        # Track usage if available
        if response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

            if llm_tokens_usage := llm_job.job_report.llm_tokens_usage:
                nb_tokens_by_category: NbTokensByCategoryDict = {
                    TokenCategory.INPUT: prompt_tokens,
                    TokenCategory.OUTPUT: output_tokens,
                }
                llm_tokens_usage.nb_tokens_by_category = nb_tokens_by_category

        # Return the generated text
        return response.text or ""

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        """Generate structured output using Google Gemini API."""
        # For structured output, we'll add instructions to output JSON
        original_prompt = llm_job.llm_prompt.user_text or ""

        # Add JSON schema instructions to the prompt
        schema_json = schema.model_json_schema()
        json_instruction = (
            f"\n\nPlease respond with a valid JSON object that matches this schema:\n"
            f"{schema_json}\n\n"
            "Respond ONLY with the JSON object, no additional text."
        )

        # Create a modified prompt
        modified_prompt = LLMPrompt(
            system_text=llm_job.llm_prompt.system_text,
            user_text=original_prompt + json_instruction,
            user_images=llm_job.llm_prompt.user_images,
        )

        # Create a modified job with the new prompt
        modified_job = LLMJob(
            llm_prompt=modified_prompt,
            job_params=llm_job.job_params,
            job_config=llm_job.job_config,
            job_metadata=llm_job.job_metadata,
            job_report=llm_job.job_report,
        )

        # Generate text response
        text_response = await self._gen_text(modified_job)

        # Parse the JSON response
        import json
        import re

        try:
            # Try to parse the entire response as JSON
            data = json.loads(text_response)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            # If parsing fails, try to extract JSON from the response
            json_match = re.search(r"\{.*\}", text_response, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return schema.model_validate(data)
                except (json.JSONDecodeError, ValueError) as e:
                    log.error(f"Failed to parse structured output: {e}")
                    log.error(f"Response was: {text_response}")
                    raise ValueError(f"Failed to parse structured output from Gemini: {e}")
            else:
                log.error(f"No JSON found in response: {text_response}")
                raise ValueError("No valid JSON found in Gemini response")

    def _prepare_contents(self, llm_prompt: LLMPrompt) -> str:
        """Prepare contents for Google Gemini API."""
        contents: List[str] = []

        # Add system message if present
        if llm_prompt.system_text:
            contents.append(f"System: {llm_prompt.system_text}")

        # Add user message
        if llm_prompt.user_text:
            contents.append(llm_prompt.user_text)

        # For now, we concatenate messages as a single string
        # The Google SDK accepts either a string or a list of content parts
        if len(contents) == 1:
            return contents[0]
        else:
            return "\n\n".join(contents)
