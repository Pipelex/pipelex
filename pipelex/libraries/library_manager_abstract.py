from abc import ABC, abstractmethod
from pathlib import Path

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_library_abstract import ConceptLibraryAbstract
from pipelex.core.domains.domain_library_abstract import DomainLibraryAbstract
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_library_abstract import PipeLibraryAbstract


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
    def open_library(self, pipeline_run_id: str) -> None:
        pass

    @abstractmethod
    def close_library(self, pipeline_run_id: str) -> None:
        pass

    @abstractmethod
    def get_domain_library(self, pipeline_run_id: str | None = None) -> DomainLibraryAbstract:
        pass

    @abstractmethod
    def get_concept_library(self, pipeline_run_id: str | None = None) -> ConceptLibraryAbstract:
        pass

    @abstractmethod
    def get_pipe_library(self, pipeline_run_id: str | None = None) -> PipeLibraryAbstract:
        pass

    @abstractmethod
    def validate_libraries(self, pipeline_run_id: str | None = None) -> None:
        pass

    @abstractmethod
    def load_libraries(
        self,
        pipeline_run_id: str | None = None,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        pass

    @abstractmethod
    def load_from_blueprint(self, blueprint: PipelexBundleBlueprint, pipeline_run_id: str | None = None) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def remove_from_blueprint(self, blueprint: PipelexBundleBlueprint, pipeline_run_id: str | None = None) -> None:
        pass
