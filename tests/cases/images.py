"""Image constants for testing."""

from typing import ClassVar


class ImageTestCases:
    """Image test constants."""

    # Directory paths
    TEST_IMAGE_DIRECTORY = "tests/data/images"

    # Individual file paths
    IMAGE_FILE_PATH_PNG = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png"

    # Remote URLs
    IMAGE_URL_PNG = "https://www.python.org/static/community_logos/python-logo-master-v3-TM.png"

    # File path collections
    IMAGE_FILE_PATHS: ClassVar[list[str]] = [
        f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png",
        f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg",
    ]

    # URL collections
    IMAGE_URLS: ClassVar[list[str]] = [
        "https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.png",
        "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
    ]
