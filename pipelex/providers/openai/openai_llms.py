from openai.types import Model

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.openai.openai_client_factory import OpenAIClientFactory


async def openai_list_available_models(
    model_handle: ModelHandle,
    *,
    backend: InferenceBackend,
) -> list[Model]:
    openai_client_async = OpenAIClientFactory.make_openai_client(
        model_handle=model_handle,
        backend=backend,
    )

    models = await openai_client_async.models.list()
    data = models.data
    return sorted(data, key=lambda model: model.id)
