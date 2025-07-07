from typing import ClassVar, List

from pipelex.tools.config.models import ConfigModel
from pipelex.tools.misc.file_utils import copy_file_from_package, copy_folder_from_package, find_files_in_dir


class LibraryConfig(ConfigModel):
    # Class variables
    package_name: ClassVar[str] = "pipelex"
    internal_library_root: ClassVar[str] = "libraries"
    exported_library_root: ClassVar[str] = "pipelex_libraries"
    internal_base_pipelines_path: ClassVar[str] = f"{internal_library_root}/pipelines"
    exported_pipelines_path: ClassVar[str] = f"{exported_library_root}/pipelines"
    exported_base_pipelines_path: ClassVar[str] = f"{exported_library_root}/pipelines/base_library"
    loaded_pipelines_path: ClassVar[str] = f"{exported_library_root}/pipelines"
    test_pipelines_path: ClassVar[str] = "tests/test_pipelines"
    internal_llm_integrations_path: ClassVar[str] = f"{internal_library_root}/llm_integrations"
    exported_llm_integrations_path: ClassVar[str] = f"{exported_library_root}/llm_integrations"
    internal_llm_deck_path: ClassVar[str] = f"{internal_library_root}/llm_deck"
    exported_llm_deck_path: ClassVar[str] = f"{exported_library_root}/llm_deck"
    internal_templates_path: ClassVar[str] = f"{internal_library_root}/templates"
    exported_templates_path: ClassVar[str] = f"{exported_library_root}/templates"
    internal_plugins_path: ClassVar[str] = f"{internal_library_root}/plugins"
    exported_plugins_path: ClassVar[str] = f"{exported_library_root}/plugins"
    failing_pipelines_path: ClassVar[str] = "tests/test_pipelines/failing_pipelines.toml"

    @classmethod
    def get_llm_deck_paths(cls) -> List[str]:
        llm_deck_paths = [str(path) for path in find_files_in_dir(dir_path=cls.exported_llm_deck_path, pattern="*.toml", is_recursive=True)]
        llm_deck_paths.sort()
        return llm_deck_paths

    @classmethod
    def get_templates_paths(cls) -> List[str]:
        return [str(path) for path in find_files_in_dir(dir_path=cls.exported_templates_path, pattern="*.toml", is_recursive=True)]

    @classmethod
    def get_plugin_config_path(cls) -> str:
        return f"{cls.exported_plugins_path}/plugin_config.toml"

    @classmethod
    def export_libraries(cls, overwrite: bool = False) -> None:
        """Duplicate pipelex libraries files in the client project, preserving directory structure."""
        # pipelines
        copy_folder_from_package(
            package_name=cls.package_name,
            folder_path_in_package=cls.internal_base_pipelines_path,
            target_dir=cls.exported_base_pipelines_path,
            overwrite=overwrite,
        )
        copy_file_from_package(
            package_name=cls.package_name,
            file_path_in_package=f"{cls.internal_library_root}/__init__.py",
            target_path=f"{cls.exported_library_root}/__init__.py",
            overwrite=overwrite,
        )
        copy_file_from_package(
            package_name=cls.package_name,
            file_path_in_package=f"{cls.internal_base_pipelines_path}/__init__.py",
            target_path=f"{cls.exported_pipelines_path}/__init__.py",
            overwrite=overwrite,
        )
        copy_file_from_package(
            package_name=cls.package_name,
            file_path_in_package=f"{cls.internal_base_pipelines_path}/__init__.py",
            target_path=f"{cls.exported_base_pipelines_path}/__init__.py",
            overwrite=overwrite,
        )

        # llm_integrations
        copy_folder_from_package(
            package_name=cls.package_name,
            folder_path_in_package=cls.internal_llm_integrations_path,
            target_dir=cls.exported_llm_integrations_path,
            overwrite=overwrite,
        )

        # llm_deck
        copy_folder_from_package(
            package_name=cls.package_name,
            folder_path_in_package=cls.internal_llm_deck_path,
            target_dir=cls.exported_llm_deck_path,
            overwrite=overwrite,
            non_overwrite_files=["overrides.toml"],
        )

        # templates
        copy_folder_from_package(
            package_name=cls.package_name,
            folder_path_in_package=cls.internal_templates_path,
            target_dir=cls.exported_templates_path,
            overwrite=overwrite,
        )

        # plugins
        copy_folder_from_package(
            package_name=cls.package_name,
            folder_path_in_package=cls.internal_plugins_path,
            target_dir=cls.exported_plugins_path,
            overwrite=overwrite,
        )
