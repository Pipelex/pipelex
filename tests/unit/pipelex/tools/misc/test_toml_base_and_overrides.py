"""`load_toml_from_base_and_overrides`: the first path is the document, the rest are optional layers."""

from pathlib import Path

import pytest

from pipelex.tools.misc.toml_utils import load_toml_from_base_and_overrides


class TestLoadTomlFromBaseAndOverrides:
    def test_the_base_alone_is_the_document(self, tmp_path: Path) -> None:
        base = tmp_path / "base.toml"
        base.write_text('[acme]\nenabled = false\nname = "Acme"\n')

        merged = load_toml_from_base_and_overrides(paths=[base, tmp_path / "absent_override.toml"])

        assert merged == {"acme": {"enabled": False, "name": "Acme"}}

    def test_a_missing_base_raises_even_when_an_override_exists(self, tmp_path: Path) -> None:
        """An override carries only the keys it sets, so it cannot stand in for the document."""
        override = tmp_path / "override.toml"
        override.write_text("[acme]\nenabled = true\n")

        with pytest.raises(FileNotFoundError):
            load_toml_from_base_and_overrides(paths=[tmp_path / "absent_base.toml", override])

    def test_an_override_merges_into_the_base_table_and_keeps_its_other_keys(self, tmp_path: Path) -> None:
        base = tmp_path / "base.toml"
        base.write_text('[acme]\nenabled = false\nname = "Acme"\n\n[other]\nenabled = true\n')
        override = tmp_path / "override.toml"
        override.write_text("[acme]\nenabled = true\n")

        merged = load_toml_from_base_and_overrides(paths=[base, override])

        assert merged == {"acme": {"enabled": True, "name": "Acme"}, "other": {"enabled": True}}

    def test_later_overrides_win_over_earlier_ones(self, tmp_path: Path) -> None:
        base = tmp_path / "base.toml"
        base.write_text('active = "base"\n')
        first = tmp_path / "first.toml"
        first.write_text('active = "first"\n')
        second = tmp_path / "second.toml"
        second.write_text('active = "second"\n')

        merged = load_toml_from_base_and_overrides(paths=[base, first, second])

        assert merged["active"] == "second"

    def test_a_list_is_replaced_not_extended(self, tmp_path: Path) -> None:
        """`deep_update` semantics: tables merge, everything else — lists included — is replaced whole."""
        base = tmp_path / "base.toml"
        base.write_text('[profile]\nfallback_order = ["a", "b"]\n')
        override = tmp_path / "override.toml"
        override.write_text('[profile]\nfallback_order = ["c"]\n')

        merged = load_toml_from_base_and_overrides(paths=[base, override])

        assert merged["profile"]["fallback_order"] == ["c"]

    def test_a_bare_path_is_refused(self, tmp_path: Path) -> None:
        """A single path where a sequence is expected would be iterated character by character."""
        base = tmp_path / "base.toml"
        base.write_text("[acme]\n")

        with pytest.raises(TypeError):
            load_toml_from_base_and_overrides(paths=base)  # type: ignore[arg-type]
