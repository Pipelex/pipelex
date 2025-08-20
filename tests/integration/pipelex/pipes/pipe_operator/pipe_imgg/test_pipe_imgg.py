import pytest

from pipelex import pretty_print
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.core.concepts.concept_native import NativeConcept
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.pipe_img_gen import PipeImgGen, PipeImgGenOutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from tests.integration.pipelex.test_data import IMGGTestCases


@pytest.mark.dry_runnable
@pytest.mark.imgg
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeImgg:
    @pytest.mark.parametrize("topic, image_desc", IMGGTestCases.IMAGE_DESC)
    async def test_pipe_img_gen(
        self,
        pipe_run_mode: PipeRunMode,
        imgg_handle: ImggHandle,
        topic: str,
        image_desc: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeImgGen(
                code="adhoc_for_test_pipe_img_gen",
                domain="generic",
                imgg_handle=imgg_handle,
                imgg_prompt=image_desc,
                output_concept_code=NativeConcept.IMAGE.code,
                output_multiplicity=False,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_imgg_output: PipeImgGenOutput = await get_pipe_router().run_pipe_job(
            pipe_job=pipe_job,
        )
        image_urls = pipe_imgg_output.image_urls[0]
        pretty_print(image_urls, title=topic)
