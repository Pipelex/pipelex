from typing import List

from openai.types import Model

from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.plugins.plugin_sdk_registry import PluginSdkHandle


async def openai_list_available_models(plugin_sdk_handle: PluginSdkHandle) -> List[Model]:
    openai_client_async = OpenAIFactory.make_openai_client(plugin_sdk_handle=plugin_sdk_handle)

    models = await openai_client_async.models.list()
    data = models.data
    sorted_data = sorted(data, key=lambda model: model.id)
    return sorted_data
