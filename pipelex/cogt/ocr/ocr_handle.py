from pipelex.types import StrEnum


class OcrHandle(StrEnum):
    BASIC_OCR = "basic/pypdfium2"
    MISTRAL_OCR = "mistral/mistral-ocr-latest"
