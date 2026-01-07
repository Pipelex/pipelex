from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.types import StrEnum


class MermaidTheme(StrEnum):
    DEFAULT = "default"
    BASE = "base"
    DARK = "dark"
    NEUTRAL = "neutral"
    FOREST = "forest"


class MermaidStyle(ConfigModel):
    """Mermaid theming preset."""

    theme: MermaidTheme = Field(strict=False)


class MermaidRenderingConfig(ConfigModel):
    """Configuration for Mermaid flowchart rendering."""

    direction: FlowchartDirection = Field(strict=False)
    is_include_data_edges: bool
    is_include_contains_edges: bool
    is_include_selected_outcome_edges: bool
    is_show_stuff_codes: bool
    style: MermaidStyle
