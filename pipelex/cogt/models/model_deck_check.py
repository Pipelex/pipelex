from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReferenceKind, ensure_model_reference
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.hub import get_model_deck


def check_llm_choice_with_deck(llm_choice: LLMModelChoice):
    if isinstance(llm_choice, LLMSetting):
        return

    model_deck = get_model_deck()
    ref = ensure_model_reference(llm_choice)

    match ref.kind:
        case ModelReferenceKind.PRESET:
            if ref.name in model_deck.llm_presets:
                return
            msg = f"LLM preset '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.LLM,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.PRESET,
                available_options=list(model_deck.llm_presets.keys()),
            )
        case ModelReferenceKind.ALIAS:
            if ref.name in model_deck.llm_aliases:
                return
            msg = f"Alias '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.LLM,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.ALIAS,
                available_options=list(model_deck.llm_aliases.keys()),
            )
        case ModelReferenceKind.WATERFALL:
            if ref.name in model_deck.llm_waterfalls:
                return
            msg = f"Waterfall '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.LLM,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.WATERFALL,
                available_options=list(model_deck.llm_waterfalls.keys()),
            )
        case ModelReferenceKind.HANDLE:
            if model_deck.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.LLM):
                return
            msg = f"Model handle '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.LLM,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.HANDLE,
                available_options=list(model_deck.inference_models.keys()),
            )


def check_extract_choice_with_deck(extract_choice: ExtractModelChoice):
    if isinstance(extract_choice, ExtractSetting):
        return

    model_deck = get_model_deck()
    ref = ensure_model_reference(extract_choice)

    match ref.kind:
        case ModelReferenceKind.PRESET:
            if ref.name in model_deck.extract_presets:
                return
            msg = f"Extract preset '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.TEXT_EXTRACTOR,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.PRESET,
                available_options=list(model_deck.extract_presets.keys()),
            )
        case ModelReferenceKind.ALIAS:
            if ref.name in model_deck.extract_aliases:
                return
            msg = f"Alias '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.TEXT_EXTRACTOR,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.ALIAS,
                available_options=list(model_deck.extract_aliases.keys()),
            )
        case ModelReferenceKind.WATERFALL:
            if ref.name in model_deck.extract_waterfalls:
                return
            msg = f"Waterfall '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.TEXT_EXTRACTOR,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.WATERFALL,
                available_options=list(model_deck.extract_waterfalls.keys()),
            )
        case ModelReferenceKind.HANDLE:
            if model_deck.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.TEXT_EXTRACTOR):
                return
            msg = f"Model handle '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.TEXT_EXTRACTOR,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.HANDLE,
                available_options=list(model_deck.inference_models.keys()),
            )


def check_search_choice_with_deck(search_choice: SearchModelChoice):
    if isinstance(search_choice, SearchSetting):
        return

    model_deck = get_model_deck()
    ref = ensure_model_reference(search_choice)

    match ref.kind:
        case ModelReferenceKind.PRESET:
            if ref.name in model_deck.search_presets:
                return
            msg = f"Search preset '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.SEARCH,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.PRESET,
                available_options=list(model_deck.search_presets.keys()),
            )
        case ModelReferenceKind.ALIAS:
            if ref.name in model_deck.search_aliases:
                return
            msg = f"Alias '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.SEARCH,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.ALIAS,
                available_options=list(model_deck.search_aliases.keys()),
            )
        case ModelReferenceKind.WATERFALL:
            if ref.name in model_deck.search_waterfalls:
                return
            msg = f"Waterfall '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.SEARCH,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.WATERFALL,
                available_options=list(model_deck.search_waterfalls.keys()),
            )
        case ModelReferenceKind.HANDLE:
            if model_deck.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.SEARCH):
                return
            msg = f"Model handle '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.SEARCH,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.HANDLE,
                available_options=list(model_deck.inference_models.keys()),
            )


def check_img_gen_choice_with_deck(img_gen_choice: ImgGenModelChoice):
    if isinstance(img_gen_choice, ImgGenSetting):
        return

    model_deck = get_model_deck()
    ref = ensure_model_reference(img_gen_choice)

    match ref.kind:
        case ModelReferenceKind.PRESET:
            if ref.name in model_deck.img_gen_presets:
                return
            msg = f"Image generation preset '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.IMG_GEN,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.PRESET,
                available_options=list(model_deck.img_gen_presets.keys()),
            )
        case ModelReferenceKind.ALIAS:
            if ref.name in model_deck.img_gen_aliases:
                return
            msg = f"Alias '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.IMG_GEN,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.ALIAS,
                available_options=list(model_deck.img_gen_aliases.keys()),
            )
        case ModelReferenceKind.WATERFALL:
            if ref.name in model_deck.img_gen_waterfalls:
                return
            msg = f"Waterfall '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.IMG_GEN,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.WATERFALL,
                available_options=list(model_deck.img_gen_waterfalls.keys()),
            )
        case ModelReferenceKind.HANDLE:
            if model_deck.is_model_handle_defined(model_handle=ref.name, model_type=ModelType.IMG_GEN):
                return
            msg = f"Model handle '{ref.name}' was not found in the model deck"
            raise ModelChoiceNotFoundError(
                message=msg,
                model_type=ModelType.IMG_GEN,
                model_choice=ref.raw,
                reference_kind=ModelReferenceKind.HANDLE,
                available_options=list(model_deck.inference_models.keys()),
            )
