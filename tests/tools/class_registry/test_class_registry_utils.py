from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.core.stuff_content import StuffContent
from pipelex.hub import get_class_registry
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from tests.tools.test_data import ClassRegistryTestCases


class TestClassRegistryUtils:
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
        ClassRegistryUtils.register_classes_in_folder(folder_path=folder, base_class=StuffContent)

        for class_name in classes_to_register:
            assert class_registry.get_class(class_name) is not None

        for class_name in classes_not_to_register:
            assert class_registry.get_class(class_name) is None

    def test_register_classes_in_folder_with_mock(self, mocker: MockerFixture):
        """Test registering classes from a folder."""
        # Mock the file finding and registration
        mock_files = [Path("/fake/file1.py"), Path("/fake/file2.py")]
        mock_find_files = mocker.patch.object(ClassRegistryUtils, "find_files_in_dir", return_value=mock_files)
        mock_register_file = mocker.patch.object(ClassRegistryUtils, "register_classes_in_file")

        ClassRegistryUtils.register_classes_in_folder(folder_path="/fake/folder", base_class=BaseModel, is_recursive=True, is_include_imported=False)

        # Verify find_files_in_dir was called correctly
        mock_find_files.assert_called_once_with(dir_path="/fake/folder", pattern="*.py", is_recursive=True)

        # Verify register_classes_in_file was called for each file
        assert mock_register_file.call_count == 2
        mock_register_file.assert_any_call(file_path="/fake/file1.py", base_class=BaseModel, is_include_imported=False)
        mock_register_file.assert_any_call(file_path="/fake/file2.py", base_class=BaseModel, is_include_imported=False)

    def test_register_classes_in_file(self, mocker: MockerFixture):
        """Test registering classes from a Python file."""
        # Mock the module utilities to avoid complex file operations
        mock_module = mocker.MagicMock()
        mock_module.__name__ = "test_module"

        # Mock the functions at the location where they're imported in ClassRegistryUtils
        mock_import = mocker.patch("pipelex.tools.class_registry_utils.import_module_from_file", return_value=mock_module)
        mock_find = mocker.patch("pipelex.tools.class_registry_utils.find_classes_in_module", return_value=[str, int])

        # Mock the global class registry
        mock_registry = mocker.MagicMock()
        mocker.patch("pipelex.tools.class_registry_utils.get_class_registry", return_value=mock_registry)

        # Mock sys.modules for cleanup verification
        mock_sys_modules = mocker.patch("pipelex.tools.class_registry_utils.sys.modules", spec=dict)

        ClassRegistryUtils.register_classes_in_file(file_path="/fake/path.py", base_class=None, is_include_imported=False)

        # Verify the mocked functions were called correctly
        mock_import.assert_called_once_with("/fake/path.py")
        mock_find.assert_called_once_with(module=mock_module, base_class=None, include_imported=False)

        # Verify sys.modules cleanup
        mock_sys_modules.__delitem__.assert_called_once_with("test_module")

        # Verify classes were registered with the global registry
        mock_registry.register_classes.assert_called_once_with(classes=[str, int])
