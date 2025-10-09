from pipelex.cogt.exceptions import ExtractChoiceNotFoundError, ImgGenChoiceNotFoundError, LLMChoiceNotFoundError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.hub import get_model_deck


def check_llm_choice_with_deck(llm_choice: LLMModelChoice):
    if isinstance(llm_choice, LLMSetting):
        return

    model_deck = get_model_deck()

    if llm_choice in model_deck.llm_presets or model_deck.is_handle_defined(model_handle=llm_choice):
        return
    msg = f"LLM choice '{llm_choice}' not found in deck"
    raise LLMChoiceNotFoundError(msg)


def check_extract_choice_with_deck(extract_choice: ExtractModelChoice):
    if isinstance(extract_choice, ExtractSetting):
        return
    model_deck = get_model_deck()
    if extract_choice in model_deck.extract_presets or model_deck.is_handle_defined(model_handle=extract_choice):
        return
    msg = f"OCR choice '{extract_choice}' not found in deck"
    raise ExtractChoiceNotFoundError(msg)


def check_img_gen_choice_with_deck(img_gen_choice: ImgGenModelChoice):
    if isinstance(img_gen_choice, ImgGenSetting):
        return
    model_deck = get_model_deck()
    if img_gen_choice in model_deck.img_gen_presets or model_deck.is_handle_defined(model_handle=img_gen_choice):
        return
    msg = f"Image generation choice '{img_gen_choice}' not found in deck"
    raise ImgGenChoiceNotFoundError(msg)
