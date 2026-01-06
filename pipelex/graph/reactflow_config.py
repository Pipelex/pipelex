from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class ReactFlowTheme(StrEnum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


class ReactFlowEdgeType(StrEnum):
    BEZIER = "bezier"
    SMOOTHSTEP = "smoothstep"
    STEP = "step"
    STRAIGHT = "straight"


class ReactFlowStyle(ConfigModel):
    """ReactFlow theming preset."""

    theme: ReactFlowTheme = Field(strict=False)


class ReactFlowRenderingConfig(ConfigModel):
    """Configuration for ReactFlow HTML rendering."""

    is_use_cdn: bool
    layout_direction: str
    nodesep: int
    ranksep: int
    edge_type: ReactFlowEdgeType = Field(strict=False)
    initial_zoom: float
    pan_to_top: bool
    default_title: str
    style: ReactFlowStyle
