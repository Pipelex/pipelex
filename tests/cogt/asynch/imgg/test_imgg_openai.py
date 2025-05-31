import base64
import os

import pytest
from openai import AsyncOpenAI

from pipelex.cogt.exceptions import ImggGenerationError
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.plugin.openai.openai_factory import OpenAIFactory
from pipelex.tools.misc.base_64_utils import save_base64_to_binary_file
from pipelex.tools.misc.file_utils import ensure_path, get_incremental_file_path
from tests.cogt.test_data import IMGGTestCases
from tests.conftest import TEST_OUTPUTS_DIR


@pytest.mark.imgg
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImggByOpenAIGpt:
    @pytest.mark.parametrize("topic, image_desc", IMGGTestCases.IMAGE_DESC)
    async def test_gpt_image_generation(self, topic: str, image_desc: str):
        client = OpenAIFactory.make_openai_client(LLMPlatform.OPENAI)
        result1 = await client.images.generate(model="gpt-image-1", prompt=image_desc, size="1024x1024")
        if not result1.data:
            raise ImggGenerationError("No result from OpenAI")

        image_base64 = result1.data[0].b64_json
        if not image_base64:
            raise ImggGenerationError("No image base64 from OpenAI")

        folder_path = f"{TEST_OUTPUTS_DIR}/imgg_by_gpt_image"
        ensure_path(folder_path)
        filename = f"gpt_imgg_{topic}"
        img_path = get_incremental_file_path(
            base_path=folder_path,
            base_name=filename,
            extension="png",
        )
        save_base64_to_binary_file(b64=image_base64, file_path=img_path)
