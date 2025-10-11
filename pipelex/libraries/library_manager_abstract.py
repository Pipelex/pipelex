from abc import ABC, abstractmethod
from pathlib import Path

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.pipes.pipe_abstract import PipeAbstract


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
    def load_libraries(self, library_dirs: list[Path] | None = None, library_file_paths: list[Path] | None = None) -> None:
        pass

    @abstractmethod
    def load_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def remove_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        pass
