"""Reading the telemetry configuration off the machine, and saying what is wrong when it will not load.

Separate from `telemetry_config.py`, which holds the models this returns, and the reason is the
import graph rather than the size. The failure path asks the migration ledger whether the files
are simply *old* — see `pipelex.core.validation` — and reaching that answer means reaching
`migration.surfaces`, the registry, which imports every configuration model there is, this
surface's included. Models and loader in one module close that into a cycle; apart, the edges run
one way: the registry reads the models, the loader reads the registry.

Same shape as `system/configuration/configs.py` beside `config_loader.py`, and the same rule the
migration work arrived at one level down: a loader must be able to reach the migration package
without reaching the registry. Deferring the import is not a way out of it — a cycle check counts
a function-level edge exactly like a module-level one.
"""

from collections.abc import Callable
from functools import partial
from pathlib import Path

from pydantic import ValidationError

from pipelex import log
from pipelex.core.validation import report_validation_error
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_surface import (
    TELEMETRY_CONFIG_SURFACE_ID,
    replay_surface_files_in_memory,
    stale_configuration_warning,
    strip_reserved_meta,
)
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.system.telemetry.telemetry_config import (
    TELEMETRY_CONFIG_FILE_NAME,
    TELEMETRY_CONFIG_OVERRIDE_FILE_NAME,
    TelemetryConfig,
)
from pipelex.tools.misc.dict_utils import apply_to_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides
from pipelex.tools.secrets.exceptions import UnknownVarPrefixError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import substitute_vars


def load_telemetry_config(*, secrets_provider: SecretsProviderAbstract) -> TelemetryConfig:
    """Load telemetry configuration from a TOML file with variable substitution.

    Files are deep-merged in this order (later wins per leaf key):

    1. ~/.pipelex/telemetry.toml (global base)
    2. ~/.pipelex/telemetry_override.toml
    3. {project_root}/.pipelex/telemetry.toml (if project dir exists and is
       distinct from the global dir)
    4. {project_root}/.pipelex/telemetry_override.toml (same condition)

    This means a project telemetry config layers *on top of* the user's global
    one rather than replacing it — secrets and personal observability settings
    declared once in ~/.pipelex/ stay in effect across all projects.

    Supports variable placeholders in string values:
    - ${VAR_NAME} -> use secrets provider by default
    - ${env:ENV_VAR_NAME} -> force use environment variable
    - ${secret:SECRET_NAME} -> force use secrets provider
    - ${env:ENV_VAR|secret:SECRET} -> try env first, then secret as fallback

    Args:
        secrets_provider: Provider for resolving secret/env variable placeholders.

    Returns:
        Validated TelemetryConfig instance.

    Raises:
        TelemetryConfigValidationError: If configuration is invalid or variable substitution fails.
    """
    global_config_dir = config_manager.global_config_dir
    telemetry_config_paths = [
        global_config_dir / TELEMETRY_CONFIG_FILE_NAME,
        global_config_dir / TELEMETRY_CONFIG_OVERRIDE_FILE_NAME,
    ]
    project_config_dir = config_manager.project_config_dir
    if project_config_dir is not None and project_config_dir != global_config_dir:
        telemetry_config_paths.append(project_config_dir / TELEMETRY_CONFIG_FILE_NAME)
        telemetry_config_paths.append(project_config_dir / TELEMETRY_CONFIG_OVERRIDE_FILE_NAME)
    telemetry_config_toml_raw = load_toml_from_path_and_merge_with_overrides(paths=telemetry_config_paths)
    strip_reserved_meta(config_dict=telemetry_config_toml_raw)

    # Apply variable substitution to all string values (keep placeholders for missing vars)
    substitute_vars_with_provider = partial(substitute_vars, secrets_provider=secrets_provider, raise_on_missing_var=False)
    try:
        telemetry_config_toml = apply_to_strings_recursive(telemetry_config_toml_raw, transform_func=substitute_vars_with_provider)
    except UnknownVarPrefixError as exc:
        paths_str = "\n".join(str(path) for path in telemetry_config_paths)
        msg = f"Variable substitution failed in telemetry configuration based on '{paths_str}': {exc}"
        raise TelemetryConfigValidationError(msg) from exc

    try:
        telemetry_config = TelemetryConfig.model_validate(telemetry_config_toml)
    except ValidationError as exc:
        recovered = _telemetry_config_the_ledger_can_explain(
            paths=telemetry_config_paths,
            substitute_vars_with_provider=substitute_vars_with_provider,
        )
        if recovered is not None:
            return recovered
        # The ledger could not carry these files onto the current shape, so what is left to say is
        # *why*: the fields the model refused, and — when a scan of this surface still finds
        # something a `pipelex migrate` would do — the pending migration that partly explains it.
        # Reaching here is not the same as "the ledger has nothing to say": the retry also
        # declines when it applied real operations and the result still would not load.
        # The scan below replays the ledger a second time, deliberately: it walks the surface's
        # whole claim (`telemetry_*.toml`, not only the files this loader merged) and runs the
        # downgrade diagnosis the retry does not, so its plans are not the retry's plans. An
        # error path over a handful of small files is the right place to pay for that.
        report = report_validation_error(validation_error=exc, surface_id=TELEMETRY_CONFIG_SURFACE_ID)
        paths_str = "\n".join(str(path) for path in telemetry_config_paths)
        msg = f"Invalid telemetry configuration in '{paths_str}':\n{report.message}"
        raise TelemetryConfigValidationError(msg, migration=report.migration) from exc
    return telemetry_config


def _telemetry_config_the_ledger_can_explain(
    *,
    paths: list[Path],
    substitute_vars_with_provider: Callable[[str], str],
) -> TelemetryConfig | None:
    """The same telemetry configuration with the ledger replayed over the user's files, or `None`.

    Boot tolerance for this surface, and it is the one that earns it today: `telemetry-config@2`
    carries the flat pre-`[custom_posthog]` file that a machine set up before that move still has,
    and such a file fails `extra="forbid"` in the field. Nothing is written — a boot warns and
    carries on, and `pipelex migrate` is what makes the change permanent.

    `None` covers both ways this declines: the ledger had nothing to say, or it did and the result
    still does not load. Substitution is re-run because it is a step of the load rather than a
    property of the files, and a placeholder it cannot read is as much a reason to decline as a
    model that refuses the shape.
    """
    replayed = replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=paths)
    if replayed is None:
        return None
    try:
        substituted = apply_to_strings_recursive(replayed.config_dict, transform_func=substitute_vars_with_provider)
        telemetry_config = TelemetryConfig.model_validate(substituted)
    except (UnknownVarPrefixError, ValidationError):
        return None
    log.warning(stale_configuration_warning(plans=replayed.plans))
    return telemetry_config
