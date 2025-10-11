"""URL constants for testing."""

from typing import ClassVar


class TestURLs:
    """Test URL constants."""

    GCP_PUBLIC = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/diagrams/gantt_tree_house.png"
    WIKIPEDIA = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ec/Olympic_rings_on_the_Eiffel_Tower_2024_%2819%29.jpg/440px-Olympic_rings_on_the_Eiffel_Tower_2024_%2819%29.jpg"

    PUBLIC_URLS: ClassVar[list[str]] = [
        GCP_PUBLIC,
        WIKIPEDIA,
    ]
