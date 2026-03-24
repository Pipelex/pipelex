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
        "talent_mappings": {
            "llm": {"creative-writer": "writing-creative"},
            "img_gen": {},
            "extract": {},
            "search": {},
        },
        "talent_mappings_usage_hint": "Use the talent name as the value for llm_talent",
    }

    def test_output_starts_with_heading(self) -> None:
        """Output should start with the main heading."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert output.startswith("# Available Models")

    def test_llm_category_present(self) -> None:
        """LLM category with data should appear as a section."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "## LLM" in output

    def test_preset_with_description(self) -> None:
        """Preset with description should show name and description."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- **writing-creative**: Creative writing" in output

    def test_preset_without_description(self) -> None:
        """Preset without description should show only the name."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- **engineering-code**" in output

    def test_aliases_use_arrow(self) -> None:
        """Aliases should use arrow notation."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- **fast** \u2192 gpt4o-mini" in output

    def test_waterfalls_show_chain(self) -> None:
        """Waterfalls should show the full fallback chain with arrows."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "gpt4o \u2192 claude-sonnet \u2192 gemini" in output

    def test_talent_mappings_present(self) -> None:
        """Talent mappings should use arrow notation."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "- **creative-writer** \u2192 writing-creative" in output

    def test_hint_present(self) -> None:
        """Usage hint should appear at the bottom."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "Use the talent name as the value for llm_talent" in output

    def test_empty_categories_omitted(self) -> None:
        """Categories with no data should not appear in output."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "## Extract" not in output
        assert "## Search" not in output

    def test_img_gen_category_present(self) -> None:
        """Image Generation category with presets should appear."""
        output = _format_models_markdown(self._FULL_RESULT)
        assert "## Image Generation" in output
        assert "- **gen-image**: Image generation" in output

    def test_all_empty_produces_heading_only(self) -> None:
        """Result with all empty sections should produce only the heading and hint."""
        empty_result: dict[str, Any] = {
            "presets": {"llm": [], "img_gen": [], "extract": [], "search": []},
            "aliases": {"llm": {}, "img_gen": {}, "extract": {}, "search": {}},
            "waterfalls": {"llm": {}, "img_gen": {}, "extract": {}, "search": {}},
            "talent_mappings": {"llm": {}, "img_gen": {}, "extract": {}, "search": {}},
            "talent_mappings_usage_hint": "hint text",
        }
        output = _format_models_markdown(empty_result)
        assert "# Available Models" in output
        assert "## LLM" not in output
        assert "hint text" in output

    def test_empty_subsections_omitted_within_category(self) -> None:
        """Within a category, subsections with no data should be omitted."""
        result: dict[str, Any] = {
            "presets": {"llm": [{"name": "only-preset"}]},
            "aliases": {"llm": {}},
            "waterfalls": {"llm": {}},
            "talent_mappings": {"llm": {}},
        }
        output = _format_models_markdown(result)
        assert "### Presets" in output
        assert "### Aliases" not in output
        assert "### Waterfalls" not in output
        assert "### Talent Mappings" not in output
