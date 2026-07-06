"""Unit tests for the shared --inputs-argument resolution against a base directory."""

from __future__ import annotations

from pathlib import Path

from pipelex.cli.commands.run._inputs_file_loader import resolve_inputs_arg_against_dir  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]


class TestResolveInputsArgAgainstDir:
    def test_relative_path_is_joined(self, tmp_path: Path) -> None:
        """A relative file path is resolved against the base directory."""
        assert resolve_inputs_arg_against_dir("inputs.toml", base_dir=tmp_path) == str(tmp_path / "inputs.toml")
        assert resolve_inputs_arg_against_dir("sub/inputs.json", base_dir=tmp_path) == str(tmp_path / "sub" / "inputs.json")

    def test_absolute_path_passes_through(self, tmp_path: Path) -> None:
        """An absolute file path is untouched."""
        absolute = str(tmp_path / "inputs.toml")
        assert resolve_inputs_arg_against_dir(absolute, base_dir=tmp_path / "elsewhere") == absolute

    def test_tilde_is_expanded(self, tmp_path: Path) -> None:
        """A `~`-prefixed path expands to the home dir, not joined under base_dir."""
        result = resolve_inputs_arg_against_dir("~/inputs.toml", base_dir=tmp_path)
        assert result == str(Path("~/inputs.toml").expanduser())
        assert "~" not in (result or "")
        assert not (result or "").startswith(str(tmp_path))

    def test_inline_json_passes_through(self, tmp_path: Path) -> None:
        """Inline JSON (a `{` prefix) is untouched."""
        assert resolve_inputs_arg_against_dir('{"topic": "cats"}', base_dir=tmp_path) == '{"topic": "cats"}'

    def test_uri_passes_through(self, tmp_path: Path) -> None:
        """A URI-scheme string is preserved unchanged, not mangled into a broken local path under base_dir."""
        assert resolve_inputs_arg_against_dir("https://example.com/inputs.json", base_dir=tmp_path) == "https://example.com/inputs.json"
        assert resolve_inputs_arg_against_dir("s3://bucket/inputs.json", base_dir=tmp_path) == "s3://bucket/inputs.json"

    def test_none_passes_through(self, tmp_path: Path) -> None:
        """None (no --inputs given) is untouched."""
        assert resolve_inputs_arg_against_dir(None, base_dir=tmp_path) is None
