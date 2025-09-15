from typing import ClassVar, List

from pipelex.tools.config.config_model import ConfigModel
from pipelex.tools.misc.file_utils import copy_file_from_package, copy_folder_from_package, find_files_in_dir

PIPELEX_LIBRARIES_PATH = "libraries"


class LibraryConfig(ConfigModel):
    package_name: ClassVar[str] = "pipelex"
    config_dir_path: str = "pipelex_libraries"

    @property
    def pipelines_dir_path(self) -> str:
        return f"{self.config_dir_path}/pipelines"

    @property
    def base_pipelines_dir_path(self) -> str:
        return f"{self.config_dir_path}/pipelines/base_library"

    @property
    def templates_dir_path(self) -> str:
        return f"{self.config_dir_path}/templates"

    @property
    def test_pipelines_dir_path(self) -> str:
        return "tests/test_pipelines"

    @property
    def failing_pipelines_file_paths(self) -> List[str]:
        return ["tests/test_pipelines/failing_pipelines.plx"]

    def get_templates_paths(self) -> List[str]:
        return [str(path) for path in find_files_in_dir(dir_path=self.templates_dir_path, pattern="*.toml", is_recursive=True)]

    def export_libraries(self, overwrite: bool = False) -> None:
        """Duplicate pipelex libraries files in the client project, preserving directory structure."""
        copy_file_from_package(
            package_name=self.package_name,
            file_path_in_package=f"{PIPELEX_LIBRARIES_PATH}/__init__.py",
            target_path=f"{self.config_dir_path}/__init__.py",
            overwrite=overwrite,
        )

        # pipelines
        copy_folder_from_package(
            package_name=self.package_name,
            folder_path_in_package=f"{PIPELEX_LIBRARIES_PATH}/pipelines",
            target_dir=self.base_pipelines_dir_path,
            overwrite=overwrite,
        )
        copy_file_from_package(
            package_name=self.package_name,
            file_path_in_package=f"{PIPELEX_LIBRARIES_PATH}/pipelines/__init__.py",
            target_path=f"{self.pipelines_dir_path}/__init__.py",
            overwrite=overwrite,
        )

        # templates
        copy_folder_from_package(
            package_name=self.package_name,
            folder_path_in_package=f"{PIPELEX_LIBRARIES_PATH}/templates",
            target_dir=self.templates_dir_path,
            overwrite=overwrite,
        )
