# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import ClassVar, List


class TestURLs:
    URL_GCP_PUBLIC = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/diagrams/gantt_tree_house.png"
    URL_WIKIPEDIA = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ec/Olympic_rings_on_the_Eiffel_Tower_2024_%2819%29.jpg/440px-Olympic_rings_on_the_Eiffel_Tower_2024_%2819%29.jpg"

    PUBLIC_URLS: ClassVar[List[str]] = [
        URL_GCP_PUBLIC,
        URL_WIKIPEDIA,
    ]


class ClassRegistryTestCases:
    MODEL_FOLDER_PATH = "tests/tools/data/mock_folder_with_classes"
    CLASSES_TO_REGISTER: ClassVar[List[str]] = [
        "Class1",
        "Class2",
        "Class3",
        "Class4",
    ]
    CLASSES_NOT_TO_REGISTER: ClassVar[List[str]] = [
        "ClassA",
        "ClassB",
    ]


class FileHelperTestCases:
    TEST_IMAGE = "tests/tools/data/images/white_square.png"
