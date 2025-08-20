from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class LibraryManagerAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def validate_libraries(self) -> None:
        pass

    @abstractmethod
    def load_libraries(self, library_dirs: Optional[List[Path]] = None, library_file_paths: Optional[List[Path]] = None) -> None:
        pass
