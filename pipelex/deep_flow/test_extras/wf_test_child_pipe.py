from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from deep_flow.log_temporal import workflow_log
    from tests.test_pipelines.tests import Mock

    from pipelex.cogt.llm.llm_models.llm_setting import LLMSettingChoices
    from pipelex.core.pipe_output import PipeOutput  # noqa: TC001
    from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
    from pipelex.hub import get_pipe_router
    from pipelex.pipe_operators.pipe_llm import PipeLLM
    from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
    from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
    from pipelex.pipeline.job_metadata import JobMetadata


class WfTestChildPipeTestCases:
    SYSTEM_PROMPT = "You are a pirate, you always talk like a pirate."
    USER_PROMPT = "In 3 sentences, tell me about the sea."
    USER_TEXT_TRICKY_1 = """
When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
How tall do you think he was when he was 12? and at 15?
"""


@workflow.defn(name="wf_test_child_pipe_llm_text")
class WfTestChildPipeLLMText:
    @workflow.run
    async def run(self) -> str | None:
        workflow_log.debug("Workflow start")
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeLLM(
                code="adhoc_for_test_child_pipe_llm_text",
                domain="adhoc",
                output_concept_code="native.Text",
                pipe_llm_prompt=PipeLLMPrompt(
                    code="adhoc_for_test_child_pipe_llm_text",
                    domain="adhoc",
                    system_prompt=WfTestChildPipeTestCases.SYSTEM_PROMPT,
                    user_text=WfTestChildPipeTestCases.USER_PROMPT,
                ),
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
        )
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_job(pipe_job)
        return pipe_output.main_stuff_as_text.text


@workflow.defn(name="wf_test_child_pipe_llm_object")
class WfTestChildPipeLLMObject:
    @workflow.run
    async def run(self) -> Mock:
        workflow_log.debug("Workflow start")
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeLLM(
                code="adhoc_for_test_child_pipe_llm_object",
                domain="adhoc",
                output_concept_code="tests.Mock",
                pipe_llm_prompt=PipeLLMPrompt(
                    code="adhoc_for_test_child_pipe_llm_object",
                    domain="adhoc",
                    user_text=WfTestChildPipeTestCases.USER_TEXT_TRICKY_1,
                ),
                llm_choices=LLMSettingChoices.make_completed_with_defaults(
                    for_object="llm_to_reason",
                ),
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
        )
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_job(pipe_job)
        llm_generated_object = pipe_output.main_stuff_as(content_type=Mock)
        assert isinstance(llm_generated_object, Mock)
        return llm_generated_object
