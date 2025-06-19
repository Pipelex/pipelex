from typing import List

import pytest

from pipelex.core.stuff_content import StuffContent
from pipelex.hub import get_class_registry
from tests.tools.test_data import ClassRegistryTestCases


class TestClassRegistry:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "folder, classes_to_register, classes_not_to_register",
        [
            (
                ClassRegistryTestCases.MODEL_FOLDER_PATH,
                ClassRegistryTestCases.CLASSES_TO_REGISTER,
                ClassRegistryTestCases.CLASSES_NOT_TO_REGISTER,
            ),
        ],
    )
    async def test_register_classes_in_folder(
        self,
        folder: str,
        classes_to_register: List[str],
        classes_not_to_register: List[str],
    ) -> None:
        class_registry = get_class_registry()
        class_registry.register_classes_in_folder(folder_path=folder, base_class=StuffContent)

        for class_name in classes_to_register:
            assert class_registry.get_class(class_name) is not None

        for class_name in classes_not_to_register:
            assert class_registry.get_class(class_name) is None
