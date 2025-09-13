from typing import Dict, Optional

from pydantic import Field, RootModel, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.exceptions import ModelCatalogError, ModelCatalogLibraryError
from pipelex.cogt.inference.model_catalog_config import ModelCatalogConfig
from pipelex.cogt.inference.model_catalog_factory import (
    ModelCatalogBlueprint,
    ModelCatalogFactory,
)
from pipelex.cogt.inference.model_catalog_provider import ModelCatalogProviderAbstract
from pipelex.config import get_config
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path

ModelCatalogLibraryRoot = Dict[str, ModelCatalogConfig]


class ModelCatalogLibrary(RootModel[ModelCatalogLibraryRoot], ModelCatalogProviderAbstract):
    """Library for managing model catalog configurations."""

    root: ModelCatalogLibraryRoot = Field(default_factory=dict)
    _active_config: Optional[str] = None

    @override
    def setup(self) -> None:
        """Set up the model catalog library."""
        pass

    @override
    def teardown(self) -> None:
        """Tear down the model catalog library."""
        self.root = {}
        self._active_config = None

    @override
    def reset(self) -> None:
        """Reset the model catalog library."""
        self.teardown()
        self.setup()

    @classmethod
    def make_empty(cls) -> "ModelCatalogLibrary":
        """Create an empty model catalog library."""
        return cls(root={})

    @override
    def load_catalog(self) -> None:
        """Load the model catalog configuration from TOML file."""
        inference_config_path = get_config().pipelex.inference_config_path
        catalog_toml_path = f"{inference_config_path}/model_catalog.toml"

        try:
            catalog_dict = load_toml_from_path(
                path=catalog_toml_path,
                is_env_var_substitution_enabled=True,
            )
        except (FileNotFoundError, TOMLValidationError) as exc:
            raise ModelCatalogLibraryError(f"Failed to load model catalog from file '{catalog_toml_path}': {exc}") from exc

        try:
            catalog_blueprint = ModelCatalogBlueprint.model_validate(catalog_dict)
        except ValidationError as exc:
            raise ModelCatalogLibraryError(f"Invalid model catalog configuration in '{catalog_toml_path}': {exc}") from exc

        # Validate that the active config exists
        if catalog_blueprint.active not in catalog_blueprint.configs:
            raise ModelCatalogLibraryError(
                f"Active configuration '{catalog_blueprint.active}' not found in catalog. "
                f"Available configurations: {list(catalog_blueprint.configs.keys())}"
            )

        # Load all configurations
        self.root = ModelCatalogFactory.make_model_catalog_configs(catalog_blueprint)
        self._active_config = catalog_blueprint.active

        log.debug(f"Loaded model catalog with active configuration: '{self._active_config}'")
        log.debug(f"Available configurations: {list(self.root.keys())}")

    @override
    def get_backend_for_model(self, model_name: str) -> str:
        """Get the backend name for a given model.

        Args:
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model

        Raises:
            ModelCatalogError: If no active configuration is set or config not found
        """
        if not self._active_config:
            raise ModelCatalogError("No active model catalog configuration loaded")

        if self._active_config not in self.root:
            raise ModelCatalogError(f"Active configuration '{self._active_config}' not found in loaded catalog")

        active_config = self.root[self._active_config]
        backend = active_config.get_backend_for_model(model_name)

        log.debug(f"Routing model '{model_name}' to backend '{backend}' using config '{self._active_config}'")
        return backend

    def get_active_config_name(self) -> Optional[str]:
        """Get the name of the currently active configuration."""
        return self._active_config

    def get_config(self, config_name: str) -> Optional[ModelCatalogConfig]:
        """Get a specific configuration by name.

        Args:
            config_name: Name of the configuration to retrieve

        Returns:
            ModelCatalogConfig if found, None otherwise
        """
        return self.root.get(config_name)

    def list_config_names(self) -> list[str]:
        """Get a list of all available configuration names."""
        return list(self.root.keys())
