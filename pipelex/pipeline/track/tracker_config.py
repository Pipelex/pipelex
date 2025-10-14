from typing import Literal

from pipelex.system.configuration.config_model import ConfigModel


class TrackerConfig(ConfigModel):
    is_debug_mode: bool
    is_include_text_preview: bool
    is_include_interactivity: bool
    theme: str | Literal["auto"]
    layout: str | Literal["auto"]
    wrapping_width: int | Literal["auto"]
    nb_items_limit: int | Literal["unlimited"]
    sub_graph_colors: list[str]
    pipe_edge_style: str
    branch_edge_style: str
    aggregate_edge_style: str
    condition_edge_style: str
    choice_edge_style: str

    @property
    def applied_theme(self) -> str | None:
        if self.theme == "auto":
            return None
        return self.theme

    @property
    def applied_layout(self) -> str | None:
        if self.layout == "auto":
            return None
        return self.layout

    @property
    def applied_wrapping_width(self) -> int | None:
        if self.wrapping_width == "auto":
            return None
        return self.wrapping_width

    @property
    def applied_nb_items_limit(self) -> int | None:
        if self.nb_items_limit == "unlimited":
            return None
        return self.nb_items_limit
