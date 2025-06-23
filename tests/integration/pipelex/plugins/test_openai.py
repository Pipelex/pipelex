import pytest

from pipelex import pretty_print
from pipelex.cogt.exceptions import LLMSDKError
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.config import get_config
from pipelex.hub import get_secrets_provider
from pipelex.plugins.openai.openai_llms import openai_list_available_models


# make t VERBOSE=2 TEST=TestOpenAI
@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
@pytest.mark.asyncio(loop_scope="class")
class TestOpenAI:
    async def test_openai_api_key(self):
        openai_config = get_config().plugins.openai_config
        assert openai_config.get_api_key(secrets_provider=get_secrets_provider())

    # pytest -k test_openai_list_available_models -s -vv
    async def test_openai_list_available_models(
        self,
        pytestconfig: pytest.Config,
        llm_platform_for_openai_sdk: LLMPlatform,
    ):
        try:
            openai_models_list = await openai_list_available_models(llm_platform=llm_platform_for_openai_sdk)
        except LLMSDKError as exc:
            if "does not support listing models" in str(exc):
                pytest.skip(f"Skipping: {exc}")
            else:
                raise exc
        if pytestconfig.get_verbosity() >= 2:
            list_of_ids = [model.id for model in openai_models_list]
            pretty_print(list_of_ids, title=f"models available for {llm_platform_for_openai_sdk}")
