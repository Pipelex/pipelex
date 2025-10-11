from openai.types import Model

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.plugins.plugin_sdk_registry import Plugin


async def openai_list_available_models(
    plugin: Plugin,
    backend: InferenceBackend,
) -> list[Model]:
    openai_client_async = OpenAIFactory.make_openai_client(
        plugin=plugin,
        backend=backend,
    )

    models = await openai_client_async.models.list()
    data = models.data
    return sorted(data, key=lambda model: model.id)
