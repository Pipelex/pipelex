from typing import Any, cast

from typing_extensions import override

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract, make_empty_prompt
from pipelex.cogt.llm.llm_prompt_template_inputs import LLMPromptTemplateInputs
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt, PipeLLMPromptOutput
from pipelex.pipeline.job_metadata import JobMetadata


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
        # llm_prompt: LLMPrompt = (
        #     await self.pipe_llm_prompt.run_pipe(
        #         pipe_run_params=PipeRunParamsFactory.make_run_params(),
        #         job_metadata=JobMetadata(session_id=get_config().session_id),
        #         working_memory=working_memory,
        #     )
        # ).llm_prompt
        # TODO: restore the possibility above, without need to explicitly cast the output
        pipe_output: PipeOutput = await self.pipe_llm_prompt.run_pipe(
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            job_metadata=JobMetadata(),
            working_memory=working_memory,
        )
        llm_prompt = cast(PipeLLMPromptOutput, pipe_output).llm_prompt
        return llm_prompt
