from pipelex.types import StrEnum


class ExtractTalent(StrEnum):
    PDF_BASIC_TEXT_EXTRACTOR = "pdf-basic-text-extractor"
    IMAGE_TEXT_EXTRACTOR = "image-text-extractor"
    FULL_DOCUMENT_EXTRACTOR = "full-document-extractor"
    WEB_PAGE_EXTRACTOR = "web-page-extractor"
