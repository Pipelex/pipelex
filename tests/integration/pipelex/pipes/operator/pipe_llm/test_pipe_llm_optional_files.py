"""A PipeLLM whose prompt reads an optional file runs when the file is not given, the shared assembly leaving it out."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import content_generator as content_generator_module
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

_BUNDLE = """
domain = "llm_optional_files"
description = "A PipeLLM whose prompt may hold a file"

[pipe.describe_damage]
type = "PipeLLM"
description = "Describe a parcel's damage"
inputs = { note = "Text", photo = "Image?", claim = "Document?" }
output = "Text"
model = "gemini-2.5-flash"
prompt = \"\"\"
A claim note: $note
@?photo
@?claim
\"\"\"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMOptionalFiles:
    async def test_absent_optional_files_are_left_out_of_the_prompt(self, mocker: MockerFixture) -> None:
        # The prompt renders in the content-generation leaf, which is where the rendered prompt is read back.
        assembly_spy = mocker.spy(content_generator_module, "render_llm_prompt")

        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY).execute(
            mthds_contents=[_BUNDLE],
            pipe_code="describe_damage",
            inputs={"note": TextContent(text="The parcel arrived with one corner crushed.")},
        )

        llm_prompt = assembly_spy.spy_return
        assert isinstance(llm_prompt, LLMPrompt)
        assert llm_prompt.user_text is not None
        assert llm_prompt.user_text.strip() == "A claim note: The parcel arrived with one corner crushed."
        assert llm_prompt.user_images == []
        assert llm_prompt.user_documents == []
        assert response.pipe_output is not None
