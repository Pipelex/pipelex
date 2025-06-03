from typing import Dict, List, Optional

import shortuuid

from pipelex.cogt.config_cogt import Cogt
from pipelex.cogt.llm.llm_models.llm_prompting_target import LLMPromptingTarget
from pipelex.exceptions import PipelexError
from pipelex.hub import get_required_config
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipeline.track.tracker_config import TrackerConfig
from pipelex.plugins.plugins_config import PluginsConfig
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.config.models import ConfigModel, ConfigRoot
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.templating.templating_models import PromptingStyle


class PipelexConfigError(PipelexError):
    pass


class PipeRunConfig(ConfigModel):
    pipe_stack_limit: int


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


class FeatureConfig(ConfigModel):
    is_pipeline_tracking_enabled: bool
    is_activity_tracking_enabled: bool


class Pipelex(ConfigModel):
    extra_env_files: List[str]
    feature_config: FeatureConfig
    log_config: LogConfig
    aws_config: AwsConfig

    library_config: LibraryConfig
    generic_template_names: GenericTemplateNames
    tracker_config: TrackerConfig
    structure_config: StructureConfig
    prompting_config: PromptingConfig

    pipe_run_config: PipeRunConfig


class PipelexConfig(ConfigRoot):
    session_id: str = shortuuid.uuid()
    cogt: Cogt
    plugins: PluginsConfig
    pipelex: Pipelex


def get_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        raise RuntimeError(f"Expected {PipelexConfig}, but got {type(singleton_config)}")
    return singleton_config
