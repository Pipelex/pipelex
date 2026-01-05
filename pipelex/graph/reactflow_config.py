from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class ReactFlowTheme(StrEnum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


class ReactFlowStyle(ConfigModel):
    """ReactFlow theming preset."""

    theme: ReactFlowTheme = Field(strict=False)


class ReactFlowRenderingConfig(ConfigModel):
    """Configuration for ReactFlow HTML rendering."""

    is_use_cdn: bool
    layout_direction: str
    nodesep: int
    ranksep: int
    default_title: str
    style: ReactFlowStyle
