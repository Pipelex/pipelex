# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any

from typing_extensions import override

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract, make_empty_prompt
from pipelex.cogt.llm.llm_prompt_template_inputs import LLMPromptTemplateInputs
from pipelex.config import get_config
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.job_metadata import JobMetadata
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt


class PipedLLMPromptFactory(LLMPromptFactoryAbstract):
    pipe_llm_prompt: PipeLLMPrompt
    proto_prompt: LLMPrompt = make_empty_prompt()
    base_template_inputs: LLMPromptTemplateInputs = LLMPromptTemplateInputs()

    @property
    @override
    def desc(self) -> str:
        return f"{PipedLLMPromptFactory.__name__} based on proto prompt: {self.proto_prompt} and base inputs: {self.base_template_inputs}"

    @override
    async def make_llm_prompt_from_args(
        self,
        **prompt_arguments: Any,
    ) -> LLMPrompt:
        arguments_dict = prompt_arguments.copy()
        working_memory = WorkingMemoryFactory.make_from_strings_from_dict(input_dict=arguments_dict)
        llm_prompt: LLMPrompt = (
            await self.pipe_llm_prompt.run_pipe(
                pipe_code="pipe_llm_prompt_from_factory",
                pipe_run_params=PipeRunParams(),
                job_metadata=JobMetadata(session_id=get_config().session_id),
                working_memory=working_memory,
            )
        ).llm_prompt
        return llm_prompt
