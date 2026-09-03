from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.exceptions import RoutingProfileDisabledBackendError, RoutingProfileLibraryError, RoutingProfileLibraryNotFoundError
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_factory import RoutingProfileFactory, RoutingProfileLibraryBlueprint
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import describe_toml_base_and_overrides, load_toml_from_base_and_overrides, present_toml_override_paths
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


def load_active_routing_profile(
    *,
    routing_profile_library_paths: Sequence[Path],
    enabled_backends: list[str],
    lenient: bool = False,
) -> RoutingProfile:
    """Load the active routing profile from the routing profile library.

    The library is one document read from several files: the base ``routing_profiles.toml``
    first, then each ``routing_profiles_override.toml`` that exists, deep-merged in order. An
    override carries only the keys it sets — ``active = "…"`` alone is a complete one — which is
    why the merge happens before validation: ``active`` is a required field of the blueprint.

    What this raises is what ``RuntimeBoot`` catches, and the classes are the contract: a missing
    base is ``RoutingProfileLibraryNotFoundError``, a file that does not parse, a document the
    blueprint refuses or an ``active`` naming no profile is ``RoutingProfileLibraryError``, and a profile whose default or
    routes name a backend that is not enabled is ``RoutingProfileDisabledBackendError``. That last
    one is the half-written override — ``active`` flipped, the backend still off — and the boot
    turns it into a setup error that says so.

    Args:
        routing_profile_library_paths: The base file first, then the override files in merge order.
        enabled_backends: List of currently enabled backend names.
        lenient: When True, warn instead of raising when the profile references
            backends that are not enabled (e.g. because credentials are missing).
    """
    library_description = describe_toml_base_and_overrides(paths=routing_profile_library_paths)
    try:
        catalog_dict = load_toml_from_base_and_overrides(paths=routing_profile_library_paths)
    except FileNotFoundError as not_found_exc:
        msg = f"Could not find routing profile library at '{routing_profile_library_paths[0]}': {not_found_exc}"
        raise RoutingProfileLibraryNotFoundError(msg) from not_found_exc
    except TomlError as toml_exc:
        msg = f"Invalid routing profile library {library_description}: {toml_exc}"
        raise RoutingProfileLibraryError(msg) from toml_exc
    if present_toml_override_paths(paths=routing_profile_library_paths):
        log.info(f"Routing profiles read from {library_description}")

    # Validate the routing profile library configuration
    try:
        routing_profile_library_blueprint = RoutingProfileLibraryBlueprint.model_validate(catalog_dict)
    except ValidationError as exc:
        valiation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid routing profile library configuration in {library_description}: {valiation_error_msg}"
        raise RoutingProfileLibraryError(msg) from exc

    # Validate that the active profile exists
    profile_names_str = ", ".join(routing_profile_library_blueprint.profiles.keys())
    active_profile_name = routing_profile_library_blueprint.active
    if active_profile_name not in routing_profile_library_blueprint.profiles:
        msg = (
            f"Active profile '{active_profile_name}' not found in the routing profile library {library_description}. "
            f"Available profiles: {profile_names_str}"
        )
        raise RoutingProfileLibraryError(msg)

    # Load all profiles
    active_profile_blueprint = routing_profile_library_blueprint.profiles[active_profile_name]
    active_profile = RoutingProfileFactory.make_routing_profile(
        name=active_profile_name,
        blueprint=active_profile_blueprint,
    )
    if active_profile.default and active_profile.default not in enabled_backends:
        if lenient:
            log.verbose(f"Default backend '{active_profile.default}' for routing profile '{active_profile_name}' is not enabled (lenient mode)")
        else:
            msg = (
                f"Default backend '{active_profile.default}' set for routing profile '{active_profile_name}' is not enabled. "
                f"You must either enable backend '{active_profile.default}' or set a different default backend for profile '{active_profile_name}', "
                "or select a different routing profile."
            )
            raise RoutingProfileDisabledBackendError(msg)

    # Check routes that use disabled backends
    seen_disabled_backends: set[str] = set()
    for backend_name in active_profile.routes.values():
        if backend_name not in enabled_backends and backend_name not in seen_disabled_backends:
            if lenient:
                log.verbose(f"Backend '{backend_name}' for profile '{active_profile_name}' is not enabled (lenient mode)")
            else:
                msg = f"Backend '{backend_name}', required for profile '{active_profile_name}' is not enabled"
                raise RoutingProfileDisabledBackendError(msg)
            seen_disabled_backends.add(backend_name)

    return active_profile
