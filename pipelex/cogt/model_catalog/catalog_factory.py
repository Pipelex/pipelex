from typing import Dict

from pydantic import Field

from pipelex.cogt.model_catalog.catalog_config import ModelCatalogConfig
from pipelex.config import ConfigModel


class ModelCatalogConfigBlueprint(ConfigModel):
    """Blueprint for creating ModelCatalogConfig instances."""

    description: str
    default: str
    routes: Dict[str, str] = Field(default_factory=dict)


class ModelCatalogBlueprint(ConfigModel):
    """Blueprint for the entire model catalog."""

    active: str
    configs: Dict[str, ModelCatalogConfigBlueprint] = Field(default_factory=dict)


class ModelCatalogFactory:
    """Factory for creating model catalog configurations."""

    @classmethod
    def make_model_catalog_config(
        cls,
        config_blueprint: ModelCatalogConfigBlueprint,
    ) -> ModelCatalogConfig:
        """Create a ModelCatalogConfig from a blueprint.

        Args:
            config_blueprint: Blueprint containing configuration data

        Returns:
            ModelCatalogConfig instance
        """
        return ModelCatalogConfig(
            description=config_blueprint.description,
            default=config_blueprint.default,
            routes=config_blueprint.routes,
        )

    @classmethod
    def make_model_catalog_configs(
        cls,
        catalog_blueprint: ModelCatalogBlueprint,
    ) -> Dict[str, ModelCatalogConfig]:
        """Create all ModelCatalogConfig instances from a catalog blueprint.

        Args:
            catalog_blueprint: Blueprint containing all configurations

        Returns:
            Dictionary mapping config names to ModelCatalogConfig instances
        """
        configs: Dict[str, ModelCatalogConfig] = {}
        for config_name, config_blueprint in catalog_blueprint.configs.items():
            configs[config_name] = cls.make_model_catalog_config(config_blueprint)
        return configs
