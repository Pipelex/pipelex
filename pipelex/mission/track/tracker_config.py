from typing import List, Literal, Optional, Union

from pipelex.tools.config.models import ConfigModel


class TrackerConfig(ConfigModel):
    is_debug_mode: bool
    is_include_text_preview: bool
    is_include_interactivity: bool
    theme: Union[str, Literal["auto"]]
    layout: Union[str, Literal["auto"]]
    wrapping_width: Union[int, Literal["auto"]]
    nb_items_limit: Union[int, Literal["unlimited"]]
    sub_graph_colors: List[str]
    pipe_edge_style: str
    branch_edge_style: str
    aggregate_edge_style: str
    condition_edge_style: str
    choice_edge_style: str

    @property
    def applied_theme(self) -> Optional[str]:
        if self.theme == "auto":
            return None
        else:
            return self.theme

    @property
    def applied_layout(self) -> Optional[str]:
        if self.layout == "auto":
            return None
        else:
            return self.layout

    @property
    def applied_wrapping_width(self) -> Optional[int]:
        if self.wrapping_width == "auto":
            return None
        else:
            return self.wrapping_width

    @property
    def applied_nb_items_limit(self) -> Optional[int]:
        if self.nb_items_limit == "unlimited":
            return None
        else:
            return self.nb_items_limit
