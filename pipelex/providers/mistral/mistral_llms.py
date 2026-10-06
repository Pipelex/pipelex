from mistralai.client.models import BaseModelCard, FTModelCard

from pipelex.providers.mistral.mistral_exceptions import MistralModelListingError
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.runtime_hub import get_models_manager


def mistral_list_available_models() -> list[BaseModelCard | FTModelCard]:
    backend = get_models_manager().get_required_inference_backend("mistral")
    mistral_client = MistralFactory.make_mistral_client(backend=backend)
    models_list_response = mistral_client.models.list()
    # The SDK keeps a card of a type it does not know as raw data, with no id or context length to list it by
    known_models = [model for model in models_list_response.data or [] if isinstance(model, (BaseModelCard, FTModelCard))]
    if not known_models:
        msg = "No models found"
        raise MistralModelListingError(msg)
    return sorted(known_models, key=lambda model: model.id)
