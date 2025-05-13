# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, List, Literal, Optional, Union

import shortuuid

from pipelex.cogt.config_cogt import Cogt
from pipelex.cogt.llm.llm_models.llm_prompting_target import LLMPromptingTarget
from pipelex.exceptions import PipelexError
from pipelex.hub import get_required_config
from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.config.models import ConfigModel, ConfigRoot
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.templating.templating_models import PromptingStyle


class PipelexConfigError(PipelexError):
    pass


class GenericTemplateNames(ConfigModel):
    structure_from_preliminary_text_user: str
    structure_from_preliminary_text_system: str


class StructureConfig(ConfigModel):
    is_default_text_then_structure: bool


class PromptingConfig(ConfigModel):
    default_prompting_style: PromptingStyle
    prompting_styles: Dict[str, PromptingStyle]

    def get_prompting_style(self, prompting_target: Optional[LLMPromptingTarget] = None) -> Optional[PromptingStyle]:
        if prompting_target:
            return self.prompting_styles.get(prompting_target, self.default_prompting_style)
        else:
            return None


class HistoryGraphConfig(ConfigModel):
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


class Pipelex(ConfigModel):
    extra_env_files: List[str]
    log_config: LogConfig
    aws_config: AwsConfig

    library_config: LibraryConfig
    generic_template_names: GenericTemplateNames
    history_graph_config: HistoryGraphConfig
    structure_config: StructureConfig
    prompting_config: PromptingConfig


class PipelexConfig(ConfigRoot):
    session_id: str = shortuuid.uuid()
    cogt: Cogt
    pipelex: Pipelex


def get_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        raise RuntimeError(f"Expected {PipelexConfig}, but got {type(singleton_config)}")
    return singleton_config
