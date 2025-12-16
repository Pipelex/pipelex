"""Image constants for testing."""

from typing import ClassVar


class ImageTestCases:
    """Image test constants."""

    # Directory paths
    TEST_IMAGE_DIRECTORY = "tests/data/images"

    # Individual file paths
    IMAGE_FILE_PATH_PNG_1 = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png"
    IMAGE_FILE_PATH_JPG_1 = f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg"
    IMAGE_FILE_PATH_JPG_2 = f"{TEST_IMAGE_DIRECTORY}/solar_system.jpg"
    IMAGE_FILE_PATH_PNG_2 = f"{TEST_IMAGE_DIRECTORY}/solar_system.png"
    IMAGE_FILE_PATH_JPG_3 = f"{TEST_IMAGE_DIRECTORY}/eiffel_tower.jpg"

    # Remote URLs
    IMAGE_URL_PNG = "https://pipelex-web.s3.amazonaws.com/tests/solar_system.png"

    # File path collections
    IMAGE_FILE_PATHS: ClassVar[list[str]] = [
        f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png",
        f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg",
    ]
    IMAGE_TEXT_FILE_PATHS: ClassVar[list[str]] = [
        IMAGE_FILE_PATH_JPG_1,
        IMAGE_FILE_PATH_PNG_2,
    ]

    # URL collections
    IMAGE_URLS: ClassVar[list[str]] = [
        "https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.png",
        "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
    ]
