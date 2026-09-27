from enum import StrEnum


class ModelType(StrEnum):
    LLM = "llm"
    TEXT_EXTRACTOR = "text_extractor"
    IMG_GEN = "img_gen"
    SEARCH = "search"

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
