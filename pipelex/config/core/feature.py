from pipelex.config.config_model import ConfigModel


class FeatureConfig(ConfigModel):
    is_pipeline_tracking_enabled: bool
    is_activity_tracking_enabled: bool
    is_reporting_enabled: bool
