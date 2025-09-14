from pipelex.cogt.exceptions import LLMPresetNotFoundError
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingOrPresetId
from pipelex.hub import get_llm_deck


def check_llm_setting_with_deck(llm_setting_or_preset_id: LLMSettingOrPresetId, is_disabled_allowed: bool = False):
    if isinstance(llm_setting_or_preset_id, LLMSetting):
        return
    preset_id: str = llm_setting_or_preset_id
    if preset_id in get_llm_deck().llm_presets:
        return
    raise LLMPresetNotFoundError(f"llm preset id '{preset_id}' not found in deck")
