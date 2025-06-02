from typing import List

from mistralai.models import Data

from pipelex.cogt.exceptions import LLMModelProviderError
from pipelex.plugins.mistral.mistral_factory import MistralFactory


def list_mistral_models() -> List[Data]:
    mistral_client = MistralFactory.make_mistral_client()
    models_list_response = mistral_client.models.list()
    if not models_list_response:
        raise LLMModelProviderError("No models found")
    models_list = models_list_response.data
    if not models_list:
        raise LLMModelProviderError("No models found")
    return sorted(models_list, key=lambda model: model.id)
