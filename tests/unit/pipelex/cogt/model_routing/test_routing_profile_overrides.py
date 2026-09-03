"""`routing_profiles_override.toml` layers over `routing_profiles.toml`, and the loader's refusals are the boot's.

The exception classes matter as much as the merge: `RuntimeBoot` catches `RoutingProfileLibraryNotFoundError`
and `RoutingProfileDisabledBackendError` to turn them into a setup error, and a half-written override — `active`
flipped to a profile whose backend is still disabled — is exactly the case that reaches those clauses.
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import RoutingProfileDisabledBackendError, RoutingProfileLibraryError, RoutingProfileLibraryNotFoundError
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile

ROUTING_PROFILES_TOML = """
active = "on_acme"

[profiles.on_acme]
description = "Everything on acme"
default = "acme"
fallback_order = ["acme", "other"]

[profiles.on_other]
description = "Everything on other"
default = "other"

[profiles.with_routes]
description = "Routes to a backend that may be off"
default = "acme"

[profiles.with_routes.routes]
"gpt-*" = "other"
"""


class TestRoutingProfileOverrides:
    def _write_base(self, tmp_path: Path) -> Path:
        base_path = tmp_path / "routing_profiles.toml"
        base_path.write_text(ROUTING_PROFILES_TOML)
        return base_path

    def test_the_base_alone_is_what_it_was(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)

        profile = load_active_routing_profile(
            routing_profile_library_paths=[base_path, tmp_path / "routing_profiles_override.toml"],
            enabled_backends=["acme"],
        )

        assert profile.name == "on_acme"
        assert profile.fallback_order == ["acme", "other"]

    def test_an_override_carrying_only_active_switches_the_profile(self, tmp_path: Path) -> None:
        """`active` is a required field, so this only works because the merge happens before validation."""
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "on_other"\n')

        profile = load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["other"])

        assert profile.name == "on_other"
        assert profile.default == "other"

    def test_an_override_can_add_a_profile_and_activate_it(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "mine"\n\n[profiles.mine]\ndescription = "Mine"\ndefault = "other"\n')

        profile = load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["other"])

        assert profile.name == "mine"
        assert profile.description == "Mine"

    def test_an_override_replaces_a_list_rather_than_extending_it(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('[profiles.on_acme]\nfallback_order = ["other"]\n')

        profile = load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["acme", "other"])

        assert profile.fallback_order == ["other"]

    def test_the_last_override_wins(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        global_override = tmp_path / "global_override.toml"
        global_override.write_text('active = "on_other"\n')
        project_override = tmp_path / "project_override.toml"
        project_override.write_text('active = "on_acme"\n')

        profile = load_active_routing_profile(
            routing_profile_library_paths=[base_path, global_override, project_override],
            enabled_backends=["acme"],
        )

        assert profile.name == "on_acme"

    def test_a_missing_base_is_not_found_even_when_an_override_exists(self, tmp_path: Path) -> None:
        absent_base = tmp_path / "absent" / "routing_profiles.toml"
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "on_other"\n')

        with pytest.raises(RoutingProfileLibraryNotFoundError) as refused:
            load_active_routing_profile(routing_profile_library_paths=[absent_base, override_path], enabled_backends=["other"])

        assert str(absent_base) in str(refused.value)

    def test_an_active_profile_that_does_not_exist_names_the_files_that_were_read(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "on_typo"\n')

        with pytest.raises(RoutingProfileLibraryError) as refused:
            load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["acme"])

        message = str(refused.value)
        assert "on_typo" in message
        assert str(base_path) in message
        assert str(override_path) in message

    def test_an_invalid_document_is_a_library_error(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text("[profiles.on_acme]\nnot_a_field = 1\n")

        with pytest.raises(RoutingProfileLibraryError):
            load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["acme"])

    def test_activating_a_profile_whose_default_backend_is_disabled_is_the_boots_disabled_backend_error(self, tmp_path: Path) -> None:
        """The half-written override: `active` flipped, the backend not enabled."""
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "on_other"\n')

        with pytest.raises(RoutingProfileDisabledBackendError) as refused:
            load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["acme"])

        assert "other" in str(refused.value)

    def test_a_route_to_a_disabled_backend_is_the_same_error(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "with_routes"\n')

        with pytest.raises(RoutingProfileDisabledBackendError):
            load_active_routing_profile(routing_profile_library_paths=[base_path, override_path], enabled_backends=["acme"])

    def test_lenient_tolerates_a_disabled_backend(self, tmp_path: Path) -> None:
        base_path = self._write_base(tmp_path)
        override_path = tmp_path / "routing_profiles_override.toml"
        override_path.write_text('active = "with_routes"\n')

        profile = load_active_routing_profile(
            routing_profile_library_paths=[base_path, override_path],
            enabled_backends=["acme"],
            lenient=True,
        )

        assert profile.name == "with_routes"
