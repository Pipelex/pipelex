from typing import Optional

import pytest

from pipelex import pretty_print
from pipelex.cogt.exceptions import LLMSDKError
from pipelex.hub import get_models_manager, get_plugin_manager, get_secrets_provider
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import PluginSdkHandle


# make t VERBOSE=2 TEST=TestOpenAI
@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
@pytest.mark.asyncio(loop_scope="class")
class TestOpenAI:
    async def test_openai_api_key(self):
        openai_config = get_plugin_manager().plugin_configs.openai_config
        assert openai_config.get_api_key(secrets_provider=get_secrets_provider())

    # pytest -k test_openai_list_available_models -s -vv
    async def test_openai_list_available_models(
        self,
        pytestconfig: pytest.Config,
        plugin_sdk_handle: PluginSdkHandle,
        backend_name: str,
        openai_endpoint: Optional[str],
    ):
        backend = get_models_manager().get_inference_backend(backend_name)
        try:
            openai_models_list = await openai_list_available_models(
                plugin_sdk_handle=plugin_sdk_handle,
                backend=backend,
                endpoint=openai_endpoint,
            )
        except LLMSDKError as exc:
            if "does not support listing models" in str(exc):
                pytest.skip(f"Skipping: {exc}")
            else:
                raise exc
        if pytestconfig.get_verbosity() >= 2:
            list_of_ids = [model.id for model in openai_models_list]
            pretty_print(list_of_ids, title=f"models available for {plugin_sdk_handle}")

        pretty_print(openai_models_list)
