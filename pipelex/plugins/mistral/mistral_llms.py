from mistralai.client.models import BaseModelCard, FTModelCard

from pipelex.hub import get_models_manager
from pipelex.plugins.mistral.mistral_exceptions import MistralModelListingError
from pipelex.plugins.mistral.mistral_factory import MistralFactory


def mistral_list_available_models() -> list[BaseModelCard | FTModelCard]:
    backend = get_models_manager().get_required_inference_backend("mistral")
    mistral_client = MistralFactory.make_mistral_client(backend=backend)
    models_list_response = mistral_client.models.list()
    if not models_list_response:
        msg = "No models found"
        raise MistralModelListingError(msg)
    models_list = models_list_response.data
    if not models_list:
        msg = "No models found"
        raise MistralModelListingError(msg)
    known_models = [model for model in models_list if isinstance(model, (BaseModelCard, FTModelCard))]
    if not known_models:
        msg = "No models found"
        raise MistralModelListingError(msg)
    return sorted(known_models, key=lambda model: model.id)
