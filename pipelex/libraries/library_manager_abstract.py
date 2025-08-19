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
    def reset(self) -> None:
        pass

    @abstractmethod
    def validate_libraries(self) -> None:
        pass

    @abstractmethod
    def load_libraries(self, library_paths: List[Path]) -> None:
        pass
