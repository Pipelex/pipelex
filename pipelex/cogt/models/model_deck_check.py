from pipelex.cogt.exceptions import LLMPresetNotFoundError
from pipelex.cogt.llm.llm_setting import LLMChoice, LLMSetting
from pipelex.hub import get_models_manager


def check_llm_setting_with_deck(llm_choice: LLMChoice):
    if isinstance(llm_choice, LLMSetting):
        return
    llm_deck = get_models_manager().get_model_deck()
    if llm_choice in llm_deck.llm_presets:
        return
    elif llm_deck.get_optional_inference_model(model_handle=llm_choice):
        return
    raise LLMPresetNotFoundError(f"LLM choice '{llm_choice}' not found in deck")
