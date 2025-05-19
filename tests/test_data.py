# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

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
    IMAGE_FILE_PATH = "tests/data/documents/solar_system.png"
    IMAGE_URL = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.png"
