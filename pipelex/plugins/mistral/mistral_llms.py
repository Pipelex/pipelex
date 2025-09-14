from typing import List

from mistralai.models import Data

from pipelex.plugins.mistral.mistral_exceptions import MistralModelListingError
from pipelex.plugins.mistral.mistral_factory import MistralFactory


def list_mistral_models() -> List[Data]:
    mistral_client = MistralFactory.make_mistral_client()
    models_list_response = mistral_client.models.list()
    if not models_list_response:
        raise MistralModelListingError("No models found")
    models_list = models_list_response.data
    if not models_list:
        raise MistralModelListingError("No models found")
    return sorted(models_list, key=lambda model: model.id)
