from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from pipelex.core.concepts.native.concept_native import NativeConceptCode
    from pipelex.core.pipes.pipe_factory import PipeFactory
    from pipelex.core.pipes.pipe_output import PipeOutput  # noqa: TC001
    from pipelex.hub import get_pipe_library, get_pipe_router
    from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
    from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
    from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
    from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
    from pipelex.pipeline.job_metadata import JobMetadata
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.test_extras.models_for_tests import Mock


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
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="LLM test for basic text generation",
            output=NativeConceptCode.TEXT,
            system_prompt=WfTestChildPipeTestCases.SYSTEM_PROMPT,
            prompt=WfTestChildPipeTestCases.USER_PROMPT,
        )
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="adhoc",
            pipe_code="adhoc_for_test_child_pipe_llm_text",
            blueprint=pipe_llm_blueprint,
        )
        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            job_metadata=JobMetadata(
                user_id="temporal_test",
                pipeline_run_id=workflow.info().workflow_id,
            ),
        )
        pipe_output: PipeOutput = await get_pipe_router().run(pipe_job=pipe_job)
        return pipe_output.main_stuff_as_text.text


@workflow.defn(name="wf_test_child_pipe_llm_object")
class WfTestChildPipeLLMObject:
    @workflow.run
    async def run(self) -> Mock:
        workflow_log.debug("Workflow start")
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="LLM test for object generation",
            output="tests.Mock",
            prompt=WfTestChildPipeTestCases.USER_TEXT_TRICKY_1,
            model_to_structure="llm_to_reason",
        )
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="adhoc",
            pipe_code="adhoc_for_test_child_pipe_llm_object",
            blueprint=pipe_llm_blueprint,
        )
        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            job_metadata=JobMetadata(
                user_id="temporal_test",
                pipeline_run_id=workflow.info().workflow_id,
            ),
        )
        pipe_output: PipeOutput = await get_pipe_router().run(pipe_job=pipe_job)
        llm_generated_object = pipe_output.main_stuff_as(content_type=Mock)
        assert isinstance(llm_generated_object, Mock)
        return llm_generated_object
