from abc import ABC, abstractmethod


class ModelCatalogProviderAbstract(ABC):
    """Abstract base class for model catalog providers."""

    @abstractmethod
    def setup(self) -> None:
        """Set up the model catalog provider."""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Tear down the model catalog provider."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the model catalog provider."""
        pass

    @abstractmethod
    def load_catalog(self) -> None:
        """Load the model catalog configuration."""
        pass

    @abstractmethod
    def get_backend_for_model(self, model_name: str) -> str:
        """Get the backend name for a given model.

        Args:
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model
        """
        pass
