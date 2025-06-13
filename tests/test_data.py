from typing import ClassVar, List


class PDFTestCases:
    DOCUMENT_FILE_PATHS: ClassVar[List[str]] = [
        # "tests/data/documents/solar_system.pdf",
        "tests/data/documents/illustrated_train_article.pdf",
    ]
    DOCUMENT_URLS: ClassVar[List[str]] = [
        "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.pdf",
    ]


# TODO: move the other shared test images here from other test_data.py files
class ImageTestCases:
    IMAGE_FILE_PATH_PNG = "tests/data/documents/solar_system.png"
    IMAGE_FILE_PATH_JPG = "tests/data/documents/solar_system.jpg"
    IMAGE_FILE_PATHS: ClassVar[List[str]] = [
        IMAGE_FILE_PATH_PNG,
        IMAGE_FILE_PATH_JPG,
    ]
    IMAGE_URL_PNG = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.png"
    IMAGE_URL_JPG = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.jpg"
    IMAGE_URLS: ClassVar[List[str]] = [
        IMAGE_URL_PNG,
        IMAGE_URL_JPG,
    ]
