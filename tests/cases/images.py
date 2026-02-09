"""Image constants for testing."""

from typing import ClassVar

from pipelex.urls import URLs


class ImageTestCases:
    """Image test constants."""

    # Directory paths
    TEST_IMAGE_DIRECTORY = "tests/data/images"

    # Individual file paths
    IMAGE_FILE_PATH_PNG_1 = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png"
    IMAGE_FILE_PATH_JPG_1 = f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg"
    IMAGE_FILE_PATH_JPG_2 = f"{TEST_IMAGE_DIRECTORY}/solar_system.jpg"
    IMAGE_FILE_PATH_PNG_2 = f"{TEST_IMAGE_DIRECTORY}/solar_system.png"
    IMAGE_FILE_PATH_PNG_3 = f"{TEST_IMAGE_DIRECTORY}/solar_system_max.png"
    IMAGE_FILE_PATH_JPG_3 = f"{TEST_IMAGE_DIRECTORY}/eiffel_tower.jpg"
    IMAGE_FILE_PATH_LOGO_TINY = f"{TEST_IMAGE_DIRECTORY}/logo-tiny.png"

    # Remote URLs
    IMAGE_URL_JPG = URLs.jpg_example_1
    IMAGE_URL_PNG = URLs.png_example_1

    # File path collections
    IMAGE_FILE_PATHS: ClassVar[list[str]] = [
        IMAGE_FILE_PATH_PNG_1,
        IMAGE_FILE_PATH_JPG_1,
    ]
    IMAGE_TEXT_FILE_PATHS: ClassVar[list[str]] = [
        IMAGE_FILE_PATH_JPG_1,
        IMAGE_FILE_PATH_PNG_2,
        IMAGE_FILE_PATH_PNG_3,
    ]

    # URL collections
    IMAGE_URLS: ClassVar[list[str]] = [
        URLs.jpg_example_1,
        URLs.jpg_example_2,
    ]

    # Base64-encoded test images for data URL testing
    # A minimal valid PNG (1x1 red pixel) - useful for unit tests
    MINIMAL_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    MINIMAL_PNG_DATA_URL = f"data:image/png;base64,{MINIMAL_PNG_BASE64}"

    # A minimal valid JPEG (1x1 pixel) - useful for unit tests
    MINIMAL_JPEG_BASE64 = (
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
        "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
        "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="
    )
    MINIMAL_JPEG_DATA_URL = f"data:image/jpeg;base64,{MINIMAL_JPEG_BASE64}"

    # Pipelex logo tiny (18x18 PNG) - useful for LLM vision tests with real image
    LOGO_TINY_PNG_BASE64 = (
        "iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAIAAADZrBkAAAAAXklEQVR4AWOgPdg9FYSQwX8c"
        "AE0Pus7/uAFhbcj2t7e3o+hkZMTpSDS/YHEqVhW4xRFswto2bdpEkjaEILHaTp06hRaSQDsJ"
        "a/v48SNmBBDW1tTUhKmBNL8NZW30BwA1YiBFn3yfOQAAAABJRU5ErkJggg=="
    )
    LOGO_TINY_PNG_DATA_URL = f"data:image/png;base64,{LOGO_TINY_PNG_BASE64}"

    # Data URL test cases for parametrize: (topic, data_url)
    DATA_URL_TEST_CASES: ClassVar[list[tuple[str, str]]] = [
        ("minimal_png", MINIMAL_PNG_DATA_URL),
        ("minimal_jpeg", MINIMAL_JPEG_DATA_URL),
    ]

    # Data URL with actual image for LLM vision test: (topic, data_url)
    DATA_URL_VISION_TEST_CASES: ClassVar[list[tuple[str, str]]] = [
        ("logo_tiny", LOGO_TINY_PNG_DATA_URL),
    ]
