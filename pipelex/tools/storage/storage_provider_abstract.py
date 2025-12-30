from abc import ABC, abstractmethod

PIPELEX_STORAGE_SCHEME = "pipelex-storage://"


class StorageProviderAbstract(ABC):
    @abstractmethod
    def load(self, uri: str) -> bytes:
        """Load data from storage.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            The stored bytes.
        """

    @abstractmethod
    def store(self, data: bytes, key: str) -> str:
        """Store data and return full URI with scheme.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).

        Returns:
            Full URI with PIPELEX_STORAGE_SCHEME prefix.
        """

    @abstractmethod
    def display_link(self, uri: str) -> str:
        """Return human-readable link for this URI.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            Human-readable link for debugging/display.
        """
