"""Slice the one fetched artifact into one gateway configuration per enabled managed backend.

Its own module rather than a method on the boot, because the doctor asks the same question the boot
does and must get the same answer: it probes a specific `backends.toml` (project vs `--global`) and
then stands up a `ModelManager` over what it found. A second implementation there would be a second
opinion on which backend reads which section.
"""

from pipelex import log
from pipelex.cogt.model_backends.backend import LEGACY_GATEWAY_MODEL_SPECS_SECTION
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.system.pipelex_service.remote_config import RemoteConfig


def build_managed_gateway_configs(
    *,
    remote_config: RemoteConfig,
    managed_gateway_sections: dict[str, str],
) -> dict[str, GatewayConfig]:
    """One gateway configuration per enabled managed backend, sliced out of the one fetched artifact.

    **One fetch, N configs, kept apart rather than merged.** The artifact is one document with one
    version, so there is exactly one network call and one disk cache; but a handle that one service
    serves and the other does not is a legitimate configuration and not a conflict to resolve, so the
    sections never meet.

    A backend whose declared section is absent from the published artifact is **disabled with a named
    warning** rather than fatal — the same posture as a managed backend missing one of its `${…}`
    variables, and for the same reason: the kit can ship a managed backend declared, so an
    installation that has not joined must not fail to boot over a section it never asked for.

    Args:
        remote_config: The artifact, fresh or from the on-disk cache.
        managed_gateway_sections: `{backend_name: section_name}`, from `enabled_managed_gateway_sections`.

    Returns:
        `{backend_name: GatewayConfig}`, carrying an entry only for a backend whose section was
        actually published.
    """
    managed_gateway_configs: dict[str, GatewayConfig] = {}
    for backend_name, section_name in managed_gateway_sections.items():
        model_specs = remote_config.get_model_specs_section(section_name)
        if model_specs is None:
            log.warning(
                f"Backend '{backend_name}' is disabled: it is a Pipelex-managed gateway backend taking its model specs from the "
                f"'{section_name}' section of the Pipelex configuration, and the configuration we read carries no such section. "
                f"Set `enabled = false` on it in your backends.toml to silence this warning."
            )
            continue
        managed_gateway_configs[backend_name] = GatewayConfig(
            model_specs=model_specs,
            # `aws_region` is a top-level key of the artifact rather than a property of a section, and
            # it belongs to the legacy gateway's slice alone: it is threaded into that backend's
            # `extra_config`, and nothing on the manifold path reads it back because there the Bedrock
            # credentials live gateway-side.
            aws_region=remote_config.aws_region if section_name == LEGACY_GATEWAY_MODEL_SPECS_SECTION else None,
        )
    return managed_gateway_configs
