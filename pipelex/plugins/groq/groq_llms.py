from openai.types import Model

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.groq.groq_factory import GroqFactory
from pipelex.plugins.plugin_sdk_registry import Plugin


async def groq_list_available_models(
    plugin: Plugin,
    backend: InferenceBackend,
) -> list[Model]:
    """List available Groq models using OpenAI-compatible client."""
    groq_client_async = GroqFactory.make_groq_client(
        plugin=plugin,
        backend=backend,
    )

    models = await groq_client_async.models.list()
    data = models.data
    return sorted(data, key=lambda model: model.id)
