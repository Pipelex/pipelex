from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.exceptions import ModelManagerError, RoutingProfileLibraryError
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_factory import RoutingProfileFactory, RoutingProfileLibraryBlueprint
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


def load_active_routing_profile(routing_profile_library_path: str, enabled_backends: list[str]) -> RoutingProfile:
    """Load the active routing profile from the routing profile library from TOML file."""
    # Load the routing profile library from TOML file
    try:
        catalog_dict = load_toml_from_path(path=routing_profile_library_path)
    except FileNotFoundError as not_found_exc:
        msg = f"Could not find routing profile library at '{routing_profile_library_path}': {not_found_exc}"
        raise ModelManagerError(msg) from not_found_exc

    # Validate the routing profile library configuration
    try:
        routing_profile_library_blueprint = RoutingProfileLibraryBlueprint.model_validate(catalog_dict)
    except ValidationError as exc:
        valiation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid routing profile library configuration in '{routing_profile_library_path}': {valiation_error_msg}"
        raise ModelManagerError(msg) from exc

    # Validate that the active profile exists
    profile_names = ", ".join(list(routing_profile_library_blueprint.profiles.keys()))
    active_profile_name = routing_profile_library_blueprint.active
    if active_profile_name not in profile_names:
        msg = f"Active profile '{active_profile_name}' not found in profile routing library. Available profiles: {profile_names}"
        raise ModelManagerError(msg)

    # Load all profiles
    active_profile_blueprint = routing_profile_library_blueprint.profiles[active_profile_name]
    active_profile = RoutingProfileFactory.make_routing_profile(
        name=active_profile_name,
        blueprint=active_profile_blueprint,
    )
    if active_profile.default and active_profile.default not in enabled_backends:
        msg = (
            f"Default backend '{active_profile.default}' set for routing profile '{active_profile_name}' is not enabled. "
            f"You must either enable backend '{active_profile.default}' or set a different default backend for profile '{active_profile_name}', "
            "or select a different routing profile."
        )
        raise RoutingProfileLibraryError(msg)

    # Raise error for routes that use disabled backends
    for backend_name in active_profile.routes.values():
        if backend_name not in enabled_backends:
            msg = f"Backend '{backend_name}', required for profile '{active_profile_name}' is not enabled"
            raise RoutingProfileLibraryError(msg)

    seen_disabled_backends: set[str] = set()
    for backend_name in active_profile.routes.values():
        if backend_name not in enabled_backends and backend_name not in seen_disabled_backends:
            msg = f"Backend '{backend_name}', required for profile '{active_profile_name}' is not enabled"
            log.info(msg)
            seen_disabled_backends.add(backend_name)
    return active_profile
