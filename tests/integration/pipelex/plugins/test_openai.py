import pytest

from pipelex import pretty_print
from pipelex.hub import get_models_manager
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin


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
        backend = get_models_manager().get_required_inference_backend(plugin_for_openai.backend)
        openai_models_list = await openai_list_available_models(
            plugin=plugin_for_openai,
            backend=backend,
        )
        if pytestconfig.get_verbosity() >= 2:
            list_of_ids = [model.id for model in openai_models_list]
            pretty_print(list_of_ids, title=f"models available for {plugin_for_openai}")

        pretty_print(openai_models_list)
