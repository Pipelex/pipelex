from pipelex.types import StrEnum


class FlowchartDirection(StrEnum):
    TOP_TO_BOTTOM = "top_to_bottom"
    TOP_DOWN = "top_down"
    BOTTOM_TO_TOP = "bottom_to_top"
    RIGHT_TO_LEFT = "right_to_left"
    LEFT_TO_RIGHT = "left_to_right"

    @property
    def mermaid_code(self) -> str:
        """Return the 2-letter Mermaid code for this direction."""
        match self:
            case FlowchartDirection.TOP_TO_BOTTOM:
                return "TB"
            case FlowchartDirection.TOP_DOWN:
                return "TD"
            case FlowchartDirection.BOTTOM_TO_TOP:
                return "BT"
            case FlowchartDirection.RIGHT_TO_LEFT:
                return "RL"
            case FlowchartDirection.LEFT_TO_RIGHT:
                return "LR"
