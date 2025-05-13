# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional

from pipelex.core.pipe import PipeAbstract


class PipeProviderAbstract(ABC):
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
