from pipelex.cogt.exceptions import LLMPresetNotFoundError
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingOrPresetId
from pipelex.cogt.model_deck.models_manager import ModelsManager
from pipelex.hub import get_models_manager


def check_llm_setting_with_deck(llm_setting_or_preset_id: LLMSettingOrPresetId):
    if isinstance(llm_setting_or_preset_id, LLMSetting):
        return
    preset_id: str = llm_setting_or_preset_id
    models_manager = get_models_manager()
    if not isinstance(models_manager, ModelsManager):
        raise RuntimeError("Models manager is not a ModelsManager")
    llm_deck = models_manager.llm_deck
    if llm_deck is None:
        raise RuntimeError("LLM deck is not initialized")
    if preset_id in llm_deck.llm_presets:
        return
    raise LLMPresetNotFoundError(f"llm preset id '{preset_id}' not found in deck")
