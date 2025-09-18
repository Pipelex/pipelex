import pytest

from pipelex import pretty_print
from pipelex.hub import get_models_manager
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.environment import any_is_placeholder_env, is_env_set


# make t VERBOSE=2 TEST=TestOpenAI
@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
@pytest.mark.asyncio(loop_scope="class")
class TestOpenAI:
    # pytest -k test_openai_list_available_models -s -vv
    async def test_openai_list_available_models(
        self,
        pytestconfig: pytest.Config,
        plugin_for_openai: Plugin,
    ):
        match plugin_for_openai.backend:
            case "openai":
                required_env_vars = ["OPENAI_API_KEY"]
            case "azure_openai":
                required_env_vars = ["AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"]
            case _:
                raise ValueError(f"Plugin {plugin_for_openai} is not supported in this test")
        if not is_env_set(required_env_vars):
            pytest.skip(f"Some key(s) missing amongst {required_env_vars}")
        if any_is_placeholder_env(required_env_vars):
            pytest.skip(f"Some key(s) among {required_env_vars} are a placeholder, can't be used to test listing models")
        backend = get_models_manager().get_required_inference_backend(plugin_for_openai.backend)
        openai_models_list = await openai_list_available_models(
            plugin=plugin_for_openai,
            backend=backend,
        )
        if pytestconfig.get_verbosity() >= 2:
            list_of_ids = [model.id for model in openai_models_list]
            pretty_print(list_of_ids, title=f"models available for {plugin_for_openai}")

        pretty_print(openai_models_list)
