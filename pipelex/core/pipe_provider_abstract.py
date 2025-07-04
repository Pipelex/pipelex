from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional

from pydantic import Field

from pipelex.core.pipe_abstract import PipeAbstract

PipeLibraryRoot = Dict[str, PipeAbstract]


class PipeProviderAbstract(ABC):
    root: PipeLibraryRoot = Field(default_factory=dict)
    _instance: ClassVar[Optional["PipeProviderAbstract"]] = None

    @abstractmethod
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        pass

    @abstractmethod
    def get_optional_pipe(self, pipe_code: str) -> Optional[PipeAbstract]:
        pass

    @abstractmethod
    def get_pipes(self) -> List[PipeAbstract]:
        pass

    @abstractmethod
    def get_pipes_dict(self) -> Dict[str, PipeAbstract]:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def pretty_list_pipes(self) -> None:
        pass

    @abstractmethod
    def add_new_pipe(self, pipe: PipeAbstract) -> None:
        pass

    @abstractmethod
    def validate_with_libraries(self) -> None:
        pass
