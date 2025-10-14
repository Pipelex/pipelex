from pydantic import field_validator

from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError


class FalConfig(ConfigModel):
    flux_map_quality_to_steps: dict[str, int]
    sdxl_lightning_map_quality_to_steps: dict[str, int]

    @field_validator("flux_map_quality_to_steps", "sdxl_lightning_map_quality_to_steps")
    @classmethod
    def validate_quality_mapping(cls, value: dict[str, int]) -> dict[str, int]:
        valid_qualities = {quality.value for quality in Quality}
        missing_qualities = valid_qualities - set(value.keys())
        invalid_qualities = set(value.keys()) - valid_qualities

        if missing_qualities and invalid_qualities:
            msg = f"Missing ({missing_qualities}) and invalid ({invalid_qualities}) quality levels in mapping"
            raise ConfigValidationError(msg)
        if missing_qualities:
            msg = f"Missing quality levels in mapping: {missing_qualities}"
            raise ConfigValidationError(msg)
        if invalid_qualities:
            msg = f"Invalid quality levels in mapping: {invalid_qualities}"
            raise ConfigValidationError(msg)
        return value
