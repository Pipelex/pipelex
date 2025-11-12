"""URL constants for testing."""

from typing import ClassVar


class TestURLs:
    """Test URL constants."""

    GCP_PUBLIC = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/diagrams/gantt_tree_house.png"
    AWS_CLOUDFRONT = "https://d2cinlfp2qnig1.cloudfront.net/tests/eiffel_tower.jpg"

    PUBLIC_URLS: ClassVar[list[str]] = [
        GCP_PUBLIC,
        AWS_CLOUDFRONT,
    ]
