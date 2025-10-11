from pipelex.types import StrEnum


class ModelType(StrEnum):
    LLM = "llm"
    TEXT_EXTRACTOR = "text_extractor"
    IMG_GEN = "img_gen"
