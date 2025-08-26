from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pipelex.core.pipes.pipe_abstract import PipeAbstract

PipeLibraryRoot = Dict[str, PipeAbstract]


class PipeProviderAbstract(ABC):
    @abstractmethod
    def validate_with_libraries(self) -> None:
        pass

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
    def add_pipes(self, pipes: List[PipeAbstract]) -> None:
        pass
