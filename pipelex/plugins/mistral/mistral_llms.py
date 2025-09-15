from typing import List

from mistralai.models import Data

from pipelex.hub import get_models_manager
from pipelex.plugins.mistral.mistral_exceptions import MistralModelListingError
from pipelex.plugins.mistral.mistral_factory import MistralFactory


def list_mistral_models() -> List[Data]:
    backend = get_models_manager().get_required_inference_backend("mistral")
    mistral_client = MistralFactory.make_mistral_client(backend=backend)
    models_list_response = mistral_client.models.list()
    if not models_list_response:
        raise MistralModelListingError("No models found")
    models_list = models_list_response.data
    if not models_list:
        raise MistralModelListingError("No models found")
    return sorted(models_list, key=lambda model: model.id)
