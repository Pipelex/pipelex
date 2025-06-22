from typing import ClassVar, List

from pipelex.core.stuff_content import StructuredContent


class PDFTestCases:
    TEST_DOCUMENT_DIRECTORY = "tests/data/documents"
    DOCUMENT_FILE_PATHS: ClassVar[List[str]] = [
        f"{TEST_DOCUMENT_DIRECTORY}/solar_system.pdf",
        f"{TEST_DOCUMENT_DIRECTORY}/illustrated_train_article.pdf",
    ]
    DOCUMENT_URLS: ClassVar[List[str]] = ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"]


class ImageTestCases:
    TEST_IMAGE_DIRECTORY = "tests/data/images"
    IMAGE_FILE_PATH_PNG = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png"
    IMAGE_URL_PNG = "https://www.python.org/static/community_logos/python-logo-master-v3-TM.png"
    IMAGE_FILE_PATHS: ClassVar[List[str]] = [
        f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png",
        f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg",
    ]
    IMAGE_URLS: ClassVar[List[str]] = [
        "https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.png",
        "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
    ]


class Article(StructuredContent):
    title: str
    description: str
    date: str
