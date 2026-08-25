from pathlib import Path
from typing import Any, cast

from pydantic import Field, ValidationError

from pipelex import log
from pipelex.cogt.model_backends.backend import PipelexBackend, resolve_model_specs_section
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.config_surface import (
    PIPELEX_SERVICE_CONFIG_SURFACE_ID,
    replay_surface_files_in_memory,
    stale_configuration_warning,
    strip_reserved_meta,
)
from pipelex.system.pipelex_service.exceptions import PipelexServiceConfigValidationError
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    PipelexServiceAgreement,
    PipelexServiceOnboarding,
)
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_from_path_if_exists
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class PipelexServiceConfig(ConfigModel):
    # A default_factory, not a required field: this is the surface's defaults layer. Every
    # in-scope configuration surface must have one, because it is what makes an additive schema
    # change absorbable and therefore never a migration — see docs/migration-ledger.md.
    agreement: PipelexServiceAgreement = Field(default_factory=PipelexServiceAgreement)
    onboarding: PipelexServiceOnboarding = Field(default_factory=PipelexServiceOnboarding)


def load_pipelex_service_config_if_exists(config_dir: Path) -> PipelexServiceConfig | None:
    """Load Pipelex service configuration if the file exists.

    Args:
        config_dir: Path to the .pipelex configuration directory.

    Returns:
        PipelexServiceConfig instance or None if file doesn't exist.
    """
    config_path = config_dir / PIPELEX_SERVICE_CONFIG_FILE_NAME
    try:
        config_toml = load_toml_from_path(path=config_path)
        strip_reserved_meta(config_dict=config_toml)
        return PipelexServiceConfig.model_validate(config_toml)
    except FileNotFoundError:
        return None
    except ValidationError as exc:
        recovered = _service_config_the_ledger_can_explain(config_path=config_path)
        if recovered is not None:
            return recovered
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid Pipelex service configuration: {validation_error_msg}"
        raise PipelexServiceConfigValidationError(msg) from exc


def _service_config_the_ledger_can_explain(*, config_path: Path) -> PipelexServiceConfig | None:
    """The same service configuration with the ledger replayed over the user's file, or `None`.

    Boot tolerance for the one surface with no tiers: a single file, so the "merge" the shared
    helper performs is a merge of one. The ledger for this surface is empty today, which makes
    this the branch that costs nothing until the first entry lands — exactly the point of wiring
    every surface at once rather than only the one that currently needs it.
    """
    replayed = replay_surface_files_in_memory(surface_id=PIPELEX_SERVICE_CONFIG_SURFACE_ID, paths=[config_path])
    if replayed is None:
        return None
    try:
        service_config = PipelexServiceConfig.model_validate(replayed.config_dict)
    except ValidationError:
        return None
    log.warning(stale_configuration_warning(plans=replayed.plans, walked_dirs=config_manager.existing_config_dirs))
    return service_config


def enabled_managed_gateway_sections(backends_file_path: Path | None = None) -> dict[str, str]:
    """The enabled managed gateway backends, each mapped to the remote-config section its specs come from.

    A *managed gateway backend* is one whose model specs arrive from the Pipelex service's published
    artifact rather than from a local per-backend TOML, and naming a section is what declares it one
    — see `resolve_model_specs_section`, which also explains why `pipelex_gateway` resolves to a
    section it never declared. There can now be more than one, which is why the boot asks this
    question rather than the single-name one below.

    Read here, off the raw TOML, for the same reason `is_pipelex_gateway_enabled` is: the boot needs
    the answer *before* it can load the backend library, because what it fetches is the input to
    that load. It applies the same truthiness reading of `enabled`, for the same reason.

    Args:
        backends_file_path: Explicit path to the ``backends.toml`` file to inspect. When ``None``
            (default), uses the layered/project-preferred path, exactly as below.

    Returns:
        ``{backend_name: section_name}``, empty when no managed gateway backend is enabled.
    """
    resolved_path = backends_file_path if backends_file_path is not None else config_manager.backends_file_path
    backends_toml = load_toml_from_path_if_exists(resolved_path)
    if backends_toml is None:
        return {}

    sections: dict[str, str] = {}
    for backend_name, backend_table in backends_toml.items():
        if not isinstance(backend_table, dict):
            continue
        backend_dict = cast("dict[str, Any]", backend_table)
        if not bool(backend_dict.get("enabled", True)):
            continue
        declared_section = backend_dict.get("model_specs_section")
        section = resolve_model_specs_section(
            backend_name=backend_name,
            declared_section=declared_section if isinstance(declared_section, str) else None,
        )
        if section is not None:
            sections[backend_name] = section
    return sections


def is_pipelex_gateway_enabled(backends_file_path: Path | None = None) -> bool:
    """Check if pipelex_gateway is enabled in the backends configuration.

    Narrower than `enabled_managed_gateway_sections` on purpose, and still the right question for
    the callers that ask it: `pipelex init`, its cache priming and the doctor's gateway probe are
    about the Portkey-cloud service specifically, not about managed backends in general.

    This reads the backends.toml file directly without loading the full backend library.

    **It must read `enabled` exactly as the library loader does** — the raw value's truthiness, and
    enabled when the key is absent — because the two are read over the same file and the boot acts
    on the answer here: it fetches the gateway's model specs only when this says enabled, then hands
    them to a loader that decides for itself which backends are enabled. Reading the literal `true`
    here while the loader read truthiness left `enabled = 1` in a state neither could name: no specs
    fetched, backend loaded — refused as *"model specs were not provided"* on a strict boot, silently
    dropped from the deck on a lenient one.

    Args:
        backends_file_path: Explicit path to the ``backends.toml`` file to inspect. When
            ``None`` (default), uses the layered/project-preferred path from
            ``config_manager.backends_file_path``. Callers that act on a specific target
            directory (e.g. ``pipelex init`` / ``pipelex init --local``) should pass the
            target's ``backends.toml`` so they don't accidentally branch on a sibling config.

    Returns:
        True if pipelex_gateway is enabled, False otherwise.
    """
    resolved_path = backends_file_path if backends_file_path is not None else config_manager.backends_file_path
    backends_toml = load_toml_from_path_if_exists(resolved_path)
    if backends_toml is None:
        return False

    gateway_config = backends_toml.get(PipelexBackend.GATEWAY)
    if gateway_config is None or not isinstance(gateway_config, dict):
        return False

    gateway_config_dict = cast("dict[str, Any]", gateway_config)
    return bool(gateway_config_dict.get("enabled", True))
