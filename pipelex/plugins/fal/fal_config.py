from typing import Dict

from pydantic import field_validator

from pipelex.cogt.imgg.imgg_job_components import Quality
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.exceptions import ConfigValidationError


class FalConfig(ConfigModel):
    flux_map_quality_to_steps: Dict[str, int]
    sdxl_lightning_map_quality_to_steps: Dict[str, int]

    @field_validator("flux_map_quality_to_steps", "sdxl_lightning_map_quality_to_steps")
    @classmethod
    def validate_quality_mapping(cls, value: Dict[str, int]) -> Dict[str, int]:
        valid_qualities = {q.value for q in Quality}
        missing_qualities = valid_qualities - set(value.keys())
        invalid_qualities = set(value.keys()) - valid_qualities

        if missing_qualities and invalid_qualities:
            raise ConfigValidationError(f"Missing ({missing_qualities}) and invalid ({invalid_qualities}) quality levels in mapping")
        elif missing_qualities:
            raise ConfigValidationError(f"Missing quality levels in mapping: {missing_qualities}")
        elif invalid_qualities:
            raise ConfigValidationError(f"Invalid quality levels in mapping: {invalid_qualities}")
        return value
