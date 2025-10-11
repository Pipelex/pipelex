import pytest

from pipelex.cogt.exceptions import ImgGenGenerationError
from pipelex.hub import get_models_manager
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.misc.base_64_utils import save_base64_to_binary_file
from pipelex.tools.misc.file_utils import ensure_path, get_incremental_file_path
from tests.conftest import TEST_OUTPUTS_DIR
from tests.integration.pipelex.test_data import ImageGenTestCases


@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImgGenByOpenAIGpt:
    @pytest.mark.parametrize(("topic", "image_desc"), ImageGenTestCases.IMAGE_DESC)
    async def test_gpt_image_generation(self, topic: str, image_desc: str):
        backend = get_models_manager().get_required_inference_backend("openai")
        client = OpenAIFactory.make_openai_client(
            Plugin(sdk="openai", backend="openai"),
            backend=backend,
        )
        result = await client.images.generate(
            prompt=image_desc,
            model="gpt-image-1",
            moderation="low",
            background="transparent",
            quality="low",
            size="1024x1024",
            output_format="png",
            output_compression=100,
            n=2,
        )
        if not result.data:
            msg = "No result from OpenAI"
            raise ImgGenGenerationError(msg)

        for image_index, image_data in enumerate(result.data):
            image_base64 = image_data.b64_json
            if not image_base64:
                msg = "No base64 image data received from OpenAI"
                raise ImgGenGenerationError(msg)

            folder_path = f"{TEST_OUTPUTS_DIR}/img_gen_by_gpt_image"
            ensure_path(folder_path)
            filename = f"{topic}_{image_index}"
            img_path = get_incremental_file_path(
                base_path=folder_path,
                base_name=filename,
                extension="png",
                avoid_suffix_if_possible=True,
            )
            save_base64_to_binary_file(b64=image_base64, file_path=img_path)
