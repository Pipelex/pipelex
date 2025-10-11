from pipelex.cogt.exceptions import ImgGenChoiceNotFoundError, LLMChoiceNotFoundError, OcrChoiceNotFoundError
from pipelex.cogt.img_gen.img_gen_setting import ImgGenChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMChoice, LLMSetting
from pipelex.cogt.ocr.ocr_setting import OcrChoice, OcrSetting
from pipelex.hub import get_model_deck


def check_llm_choice_with_deck(llm_choice: LLMChoice):
    if isinstance(llm_choice, LLMSetting):
        return

    llm_deck = get_model_deck()

    if llm_choice in llm_deck.llm_presets or llm_deck.is_handle_defined(model_handle=llm_choice):
        return
    msg = f"LLM choice '{llm_choice}' not found in deck"
    raise LLMChoiceNotFoundError(msg)


def check_ocr_choice_with_deck(ocr_choice: OcrChoice):
    if isinstance(ocr_choice, OcrSetting):
        return
    ocr_deck = get_model_deck()
    if ocr_choice in ocr_deck.ocr_presets or ocr_deck.is_handle_defined(model_handle=ocr_choice):
        return
    msg = f"OCR choice '{ocr_choice}' not found in deck"
    raise OcrChoiceNotFoundError(msg)


def check_img_gen_choice_with_deck(img_gen_choice: ImgGenChoice):
    if isinstance(img_gen_choice, ImgGenSetting):
        return
    img_gen_deck = get_model_deck()
    if img_gen_choice in img_gen_deck.img_gen_presets or img_gen_deck.is_handle_defined(model_handle=img_gen_choice):
        return
    msg = f"Image generation choice '{img_gen_choice}' not found in deck"
    raise ImgGenChoiceNotFoundError(msg)
