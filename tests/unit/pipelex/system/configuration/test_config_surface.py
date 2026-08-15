"""Unit tests for the reserved `[meta]` strip shared by every configuration surface.

The key is reserved so a later project can stamp a schema version into a file without that
being a breaking change today. Nothing writes it, but every configuration-surface reader must
already tolerate it — otherwise the first file that carries one fails an `extra="forbid"`
model and takes the boot with it.
"""

from typing import Any

from pipelex.system.configuration.config_surface import strip_reserved_meta


class TestStripReservedMeta:
    def test_the_reserved_key_is_removed_with_its_now_empty_table(self) -> None:
        """The whole `[meta]` goes when `schema_version` was all it held."""
        config_dict: dict[str, Any] = {"meta": {"schema_version": 3}, "pipelex": {"kept": True}}
        strip_reserved_meta(config_dict=config_dict)
        assert config_dict == {"pipelex": {"kept": True}}

    def test_a_meta_table_with_other_keys_keeps_them(self) -> None:
        """Only the reserved key is ours to strip.

        Anything else under `[meta]` is not reserved, so it must go on failing validation
        loudly rather than being swallowed along with the key that is.
        """
        config_dict: dict[str, Any] = {"meta": {"schema_version": 3, "something_else": "x"}}
        strip_reserved_meta(config_dict=config_dict)
        assert config_dict == {"meta": {"something_else": "x"}}

    def test_a_configuration_without_the_key_is_untouched(self) -> None:
        """The overwhelmingly common case — nothing writes the key — costs nothing."""
        config_dict: dict[str, Any] = {"pipelex": {"kept": True}}
        strip_reserved_meta(config_dict=config_dict)
        assert config_dict == {"pipelex": {"kept": True}}

    def test_a_non_table_meta_is_left_for_validation_to_reject(self) -> None:
        """`meta = "oops"` is not the reserved shape, so it is not this helper's to remove."""
        config_dict: dict[str, Any] = {"meta": "oops"}
        strip_reserved_meta(config_dict=config_dict)
        assert config_dict == {"meta": "oops"}
