from pipelex.cogt.exceptions import LLMPresetNotFoundError
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingOrPresetId
from pipelex.hub import get_models_manager


def check_llm_setting_with_deck(llm_setting_or_preset_id: LLMSettingOrPresetId):
    if isinstance(llm_setting_or_preset_id, LLMSetting):
        return
    preset_id: str = llm_setting_or_preset_id
    llm_deck = get_models_manager().get_llm_deck()
    if preset_id in llm_deck.llm_presets:
        return
    raise LLMPresetNotFoundError(f"llm preset id '{preset_id}' not found in deck")
