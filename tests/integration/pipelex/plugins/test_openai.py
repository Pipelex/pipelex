import pytest

from pipelex import pretty_print
from pipelex.hub import get_models_manager
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.system.environment import all_env_vars_are_set, any_env_var_is_placeholder
from tests.integration.pipelex.plugins.conftest import is_backend_available


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
        if not is_backend_available(plugin_for_openai.backend):
            pytest.skip(f"Backend '{plugin_for_openai.backend}' is not available or enabled")
        match plugin_for_openai.backend:
            case "openai":
                required_env_vars = ["OPENAI_API_KEY"]
            case "azure_openai":
                required_env_vars = ["AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"]
            case _:
                msg = f"Plugin {plugin_for_openai} is not supported in this test"
                raise ValueError(msg)
        if not all_env_vars_are_set(keys=required_env_vars):
            pytest.skip(f"Some key(s) missing amongst {required_env_vars}")
        if any_env_var_is_placeholder(required_env_vars):
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
