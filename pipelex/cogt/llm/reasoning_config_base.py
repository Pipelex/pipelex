from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.system.exceptions import ConfigValidationError

EffortToLevelMap = dict[str, str]
DISABLED_LEVEL = "disabled"


def validate_effort_to_level_map(effort_to_level_map: EffortToLevelMap, config_name: str) -> EffortToLevelMap:
    """Check all ReasoningEffort values are present as keys."""
    valid_efforts = {effort.value for effort in ReasoningEffort}
    missing_efforts = valid_efforts - set(effort_to_level_map.keys())
    invalid_efforts = set(effort_to_level_map.keys()) - valid_efforts
    if missing_efforts and invalid_efforts:
        msg = f"Missing ({missing_efforts}) and invalid ({invalid_efforts}) reasoning effort levels in {config_name}"
        raise ConfigValidationError(msg)
    if missing_efforts:
        msg = f"Missing reasoning effort levels in {config_name}: {missing_efforts}"
        raise ConfigValidationError(msg)
    if invalid_efforts:
        msg = f"Invalid reasoning effort levels in {config_name}: {invalid_efforts}"
        raise ConfigValidationError(msg)
    return effort_to_level_map


def get_reasoning_level_str(effort_to_level_map: EffortToLevelMap, effort: ReasoningEffort) -> str | None:
    """Look up effort in the map, return None for 'disabled'."""
    level = effort_to_level_map.get(effort)
    if level is None:
        msg = f"No level found for reasoning effort '{effort}'"
        raise ConfigValidationError(msg)
    if level == DISABLED_LEVEL:
        return None
    return level
