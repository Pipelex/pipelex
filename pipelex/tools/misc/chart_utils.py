from enum import StrEnum


class FlowchartDirection(StrEnum):
    """Flowchart layout direction.

    This is the single source of truth for direction naming across all renderers.
    External formats (Mermaid, ReactFlow/Dagre) use different codes which are
    provided via properties for last-mile conversion.
    """

    TOP_DOWN = "top_down"
    LEFT_TO_RIGHT = "left_to_right"

    @property
    def mermaid_code(self) -> str:
        """Return the Mermaid code for this direction (TD or LR)."""
        match self:
            case FlowchartDirection.TOP_DOWN:
                return "TD"
            case FlowchartDirection.LEFT_TO_RIGHT:
                return "LR"

    @property
    def reactflow_code(self) -> str:
        """Return the ReactFlow/Dagre code for this direction (TB or LR)."""
        match self:
            case FlowchartDirection.TOP_DOWN:
                return "TB"
            case FlowchartDirection.LEFT_TO_RIGHT:
                return "LR"
