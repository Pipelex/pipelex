from enum import StrEnum
from typing import Final


class ModelType(StrEnum):
    LLM = "llm"
    TEXT_EXTRACTOR = "text_extractor"
    IMG_GEN = "img_gen"
    SEARCH = "search"
    DOC_GEN = "doc_gen"
    JUDGMENT = "judgment"

    @property
    def indefinite_description(self) -> str:
        """The kind of model this type is, in prose with its indefinite article, for advice such as a next step."""
        match self:
            case ModelType.LLM:
                return "an LLM"
            case ModelType.TEXT_EXTRACTOR:
                return "a text-extraction model"
            case ModelType.IMG_GEN:
                return "an image-generation model"
            case ModelType.SEARCH:
                return "a search model"
            case ModelType.DOC_GEN:
                return "a document-generation engine"
            case ModelType.JUDGMENT:
                return "a judgment model"


DEFAULT_MODEL_TYPE: Final[ModelType] = ModelType.LLM
"""The model type of a model spec that declares none, in its own table or in its file's `[defaults]`."""
