from typing import Callable

import pytest

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.method_hub import get_pipe_router
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.fixtures.model_combo import ModelCombo
from tests.integration.pipelex.test_data import ImageGenTestCases


@pytest.mark.dry_runnable
@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeImgGenRun:
    @pytest.mark.parametrize(("topic", "prompt", "negative_prompt"), ImageGenTestCases.IMAGE_GEN_PROMPT_CONTENTS)
    async def test_pipe_img_gen_run_no_inputs(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        img_gen_combo: ModelCombo,
        topic: str,  # noqa: ARG002
        prompt: str,
        negative_prompt: str | None,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        pipe_img_gen_blueprint = PipeImgGenBlueprint(
            description="Image generation test",
            model=img_gen_combo.handle,
            output=NativeConceptCode.IMAGE,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_test_pipe_img_gen",
                blueprint=pipe_img_gen_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
        )
        await get_pipe_router().run(
            pipe_job=pipe_job,
        )

    @pytest.mark.parametrize(("topic", "image_desc", "negative_prompt"), ImageGenTestCases.IMAGE_GEN_PROMPT_CONTENTS)
    async def test_pipe_img_gen_run_input_to_template(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        img_gen_combo: ModelCombo,
        topic: str,  # noqa: ARG002
        image_desc: str,
        negative_prompt: str | None,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        pipe_img_gen_blueprint = PipeImgGenBlueprint(
            description="Image generation test",
            model=img_gen_combo.handle,
            inputs={"image_desc": "Text"},
            output=NativeConceptCode.IMAGE,
            prompt="Sketch black and white funny illustration of: $image_desc",
            negative_prompt=negative_prompt,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_test_pipe_img_gen",
                blueprint=pipe_img_gen_blueprint,
            ),
            working_memory=WorkingMemoryFactory.make_from_single_stuff(
                stuff=StuffFactory.make_from_str(str_value=image_desc, name="image_desc"),
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
        )
        await get_pipe_router().run(
            pipe_job=pipe_job,
        )
