import pytest
from pydantic import ValidationError

from pipelex.config import get_config
from pipelex.system.configuration.configs import PipelineExecutionConfig


class TestPipelineExecutionConfig:
    def test_rejects_max_wait_below_base_wait(self):
        """A transient_retry_max_wait lower than transient_retry_base_wait is an invalid retry policy."""
        config_data = get_config().pipelex.pipeline_execution_config.model_dump()
        config_data["transient_retry_base_wait"] = 10.0
        config_data["transient_retry_max_wait"] = 5.0

        with pytest.raises(ValidationError, match="transient_retry_max_wait"):
            PipelineExecutionConfig.model_validate(config_data)

    def test_accepts_max_wait_at_or_above_base_wait(self):
        """A transient_retry_max_wait equal to (or above) transient_retry_base_wait is accepted."""
        config_data = get_config().pipelex.pipeline_execution_config.model_dump()
        config_data["transient_retry_base_wait"] = 5.0
        config_data["transient_retry_max_wait"] = 5.0

        validated = PipelineExecutionConfig.model_validate(config_data)
        assert validated.transient_retry_base_wait == 5.0
        assert validated.transient_retry_max_wait == 5.0
