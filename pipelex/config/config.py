from pipelex.config.config_root import ConfigRoot
from pipelex.config.core.cogt import Cogt
from pipelex.config.core.dry_run import DryRunConfig, StaticValidationConfig
from pipelex.config.core.feature import FeatureConfig
from pipelex.config.core.observer import ObserverConfig
from pipelex.config.core.pipe import PipeRunConfig
from pipelex.config.core.prompting import PromptingConfig
from pipelex.config.core.reporting import ReportingConfig
from pipelex.config.core.structure import StructureConfig
from pipelex.config.core.templates import TemplatesConfig
from pipelex.hub import get_required_config
from pipelex.language.plx_config import PlxConfig
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipeline.track.tracker_config import TrackerConfig
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.log.log_config import LogConfig


class PipelexConfig(ConfigRoot):
    cogt: Cogt
    feature_config: FeatureConfig
    log_config: LogConfig
    aws_config: AwsConfig

    library_config: LibraryConfig
    static_validation_config: StaticValidationConfig
    templates_config: TemplatesConfig
    tracker_config: TrackerConfig
    structure_config: StructureConfig
    prompting_config: PromptingConfig
    plx_config: PlxConfig

    dry_run_config: DryRunConfig
    pipe_run_config: PipeRunConfig
    reporting_config: ReportingConfig
    observer_config: ObserverConfig


def get_pipelex_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        msg = f"Expected {PipelexConfig}, but got {type(singleton_config)}"
        raise TypeError(msg)
    return singleton_config
