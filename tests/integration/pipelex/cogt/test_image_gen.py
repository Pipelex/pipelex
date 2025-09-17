import pytest

from pipelex import pretty_print
from pipelex.cogt.imgg.imgg_job_factory import ImggJobFactory
from pipelex.hub import get_imgg_worker
from tests.integration.pipelex.test_data import IMGGTestCases


@pytest.mark.imgg
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageGeneration:
    @pytest.mark.parametrize("topic, imgg_prompt_text", IMGGTestCases.IMAGE_DESC)
    async def test_imgg_using_handle(self, imgg_handle: str, topic: str, imgg_prompt_text: str):
        imgg_worker_async = get_imgg_worker(imgg_handle=imgg_handle)
        imgg_job = ImggJobFactory.make_imgg_job_from_prompt_contents(
            positive_text=imgg_prompt_text,
        )
        generated_image = await imgg_worker_async.gen_image(
            imgg_job=imgg_job,
        )
        pretty_print(generated_image, title=f"Generated Image, topic={topic}, imgg_handle={imgg_handle}")
