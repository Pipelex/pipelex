from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class LibraryManagerAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def load_combo_libraries(self, library_paths: List[Path]):
        pass

    @abstractmethod
    def get_plugin_config_path(self) -> str:
        pass
