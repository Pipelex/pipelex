from enum import StrEnum

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.chart_utils import FlowchartDirection


class ReactFlowTheme(StrEnum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


class ReactFlowPalette(StrEnum):
    YELLOW_BLUE = "yellow_blue"
    DRACULA = "dracula"


class ReactFlowEdgeType(StrEnum):
    BEZIER = "bezier"
    SMOOTHSTEP = "smoothstep"
    STEP = "step"
    STRAIGHT = "straight"


class ReactFlowStyle(ConfigModel):
    """ReactFlow theming preset."""

    theme: ReactFlowTheme = Field(strict=False)
    palette: ReactFlowPalette = Field(strict=False)


class ReactFlowRenderingConfig(ConfigModel):
    """Configuration for ReactFlow HTML rendering."""

    is_use_cdn: bool
    layout_direction: FlowchartDirection = Field(strict=False)
    nodesep: int
    ranksep: int
    edge_type: ReactFlowEdgeType = Field(strict=False)
    initial_zoom: float
    pan_to_top: bool
    default_title: str
    style: ReactFlowStyle
    # When True, PipeBatch controller nodes appear in the graph as pipe nodes for batch edges
    # When False, batch edges connect stuff nodes directly (list -> items, items -> list)
    show_batch_controller: bool
