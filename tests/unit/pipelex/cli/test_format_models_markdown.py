"""Unit tests for the models command markdown formatter."""

from __future__ import annotations

from typing import Any, ClassVar

from pipelex.cli.agent_cli.commands.models_cmd import (
    _format_models_markdown,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
)


class TestFormatModelsMarkdown:
    """Tests for _format_models_markdown output."""

    _FULL_RESULT: ClassVar[dict[str, Any]] = {
        "success": True,
        "presets": {
            "llm": [
                {"name": "writing-creative", "description": "Creative writing"},
                {"name": "engineering-code"},
            ],
            "img_gen": [{"name": "gen-image", "description": "Image generation"}],
            "extract": [],
            "search": [],
        },
        "aliases": {
            "llm": {"fast": "gpt4o-mini", "smart": "claude-sonnet"},
            "img_gen": {},
            "extract": {},
            "search": {},
        },
        "waterfalls": {
            "llm": {"robust": ["gpt4o", "claude-sonnet", "gemini"]},
            "img_gen": {},
            "extract": {},
            "search": {},
        },
    }

    def test_output_starts_with_heading(self) -> None:
        """Output should start with the main heading."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert output.startswith("# Available Models")

    def test_llm_category_present(self) -> None:
        """LLM category with data should appear as a section."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "## LLM" in output

    def test_preset_with_description_uses_sigil(self) -> None:
        """Preset with description should show $-prefixed name and description."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- $writing-creative: Creative writing" in output

    def test_preset_without_description_uses_sigil(self) -> None:
        """Preset without description should show only the $-prefixed name."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- $engineering-code" in output

    def test_aliases_use_sigil_and_arrow(self) -> None:
        """Aliases should use @-prefix and arrow notation."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- @fast \u2192 gpt4o-mini" in output

    def test_waterfalls_use_sigil_and_chain(self) -> None:
        """Waterfalls should use ~-prefix and show the full fallback chain."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- ~robust: gpt4o \u2192 claude-sonnet \u2192 gemini" in output

    def test_no_bold_markers(self) -> None:
        """Output should not contain bold markdown markers."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "**" not in output

    def test_empty_categories_omitted(self) -> None:
        """Categories with no data should not appear in output."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "## Extract" not in output
        assert "## Search" not in output

    def test_img_gen_category_present(self) -> None:
        """Image Generation category with presets should appear with sigil."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "## Image Generation" in output
        assert "- $gen-image: Image generation" in output

    def test_all_empty_produces_heading_only(self) -> None:
        """Result with all empty sections should produce only the heading."""
        empty_result: dict[str, Any] = {
            "presets": {"llm": [], "img_gen": [], "extract": [], "search": []},
            "aliases": {"llm": {}, "img_gen": {}, "extract": {}, "search": {}},
            "waterfalls": {"llm": {}, "img_gen": {}, "extract": {}, "search": {}},
        }
        output = _format_models_markdown(empty_result)
        assert "# Available Models" in output
        assert "## LLM" not in output

    def test_empty_subsections_omitted_within_category(self) -> None:
        """Within a category, subsections with no data should be omitted."""
        result: dict[str, Any] = {
            "presets": {"llm": [{"name": "only-preset"}]},
            "aliases": {"llm": {}},
            "waterfalls": {"llm": {}},
        }
        output = _format_models_markdown(result)
        assert "### Presets" in output
        assert "### Aliases" not in output
        assert "### Waterfalls" not in output

    def test_presets_description_line(self) -> None:
        """Presets section should include the one-liner description."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "Presets are the preferred way to specify models" in output

    def test_aliases_description_line(self) -> None:
        """Aliases section should include the one-liner description."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "Aliases provide stable names" in output
