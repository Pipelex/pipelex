from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class InferenceBackendProviderAbstract(ABC):
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
    def load_backends(self) -> None:
        pass
