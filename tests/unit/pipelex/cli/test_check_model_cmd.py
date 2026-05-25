"""Unit tests for the agent CLI check-model command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

from pipelex.builder.operations.models_ops import ModelCategory
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.check_model_cmd import agent_check_model_cmd
from pipelex.cogt.model_backends.model_type import ModelType

MODULE_PATH = "pipelex.cli.agent_cli.commands.check_model_cmd"


class _FakeSetting:
    """Minimal stand-in for LLMSetting / ExtractSetting."""

    def __init__(self, model: str, description: str | None = None):
        self.model = model
        self.description = description


class _FakeInferenceModelSpec:
    """Minimal stand-in for InferenceModelSpec."""

    def __init__(self, model_type: ModelType):
        self.model_type = model_type


class TestData:
    """Shared test data constants."""

    LLM_PRESETS: ClassVar[dict[str, _FakeSetting]] = {
        "writing-creative": _FakeSetting(model="claude-sonnet", description="Creative writing"),
        "writing-factual": _FakeSetting(model="claude-sonnet", description="Factual writing"),
        "deep-analysis": _FakeSetting(model="claude-opus", description="Deep analysis"),
    }
    LLM_ALIASES: ClassVar[dict[str, str]] = {
        "best-claude": "claude-sonnet",
        "best-gpt": "gpt-4o",
        "default-general": "claude-sonnet",
    }
    LLM_WATERFALLS: ClassVar[dict[str, list[str]]] = {
        "robust-llm": ["claude-sonnet", "gpt-4o"],
    }
    INFERENCE_MODELS: ClassVar[dict[str, _FakeInferenceModelSpec]] = {
        "claude-4.5-sonnet": _FakeInferenceModelSpec(model_type=ModelType.LLM),
        "claude-4-sonnet": _FakeInferenceModelSpec(model_type=ModelType.LLM),
        "claude-4.6-opus": _FakeInferenceModelSpec(model_type=ModelType.LLM),
        "gpt-4o": _FakeInferenceModelSpec(model_type=ModelType.LLM),
        "gpt-4o-mini": _FakeInferenceModelSpec(model_type=ModelType.LLM),
    }

    EXTRACT_PRESETS: ClassVar[dict[str, Any]] = {}
    EXTRACT_ALIASES: ClassVar[dict[str, str]] = {}
    EXTRACT_WATERFALLS: ClassVar[dict[str, list[str]]] = {}
    IMG_GEN_PRESETS: ClassVar[dict[str, Any]] = {}
    IMG_GEN_ALIASES: ClassVar[dict[str, str]] = {}
    IMG_GEN_WATERFALLS: ClassVar[dict[str, list[str]]] = {}
    SEARCH_PRESETS: ClassVar[dict[str, Any]] = {}
    SEARCH_ALIASES: ClassVar[dict[str, str]] = {}
    SEARCH_WATERFALLS: ClassVar[dict[str, list[str]]] = {}


def _make_fake_model_deck() -> Any:
    """Create a fake ModelDeck with LLM test data."""

    class FakeModelDeck:
        llm_presets = TestData.LLM_PRESETS
        llm_aliases = TestData.LLM_ALIASES
        llm_waterfalls = TestData.LLM_WATERFALLS
        inference_models = TestData.INFERENCE_MODELS

        extract_presets = TestData.EXTRACT_PRESETS
        extract_aliases = TestData.EXTRACT_ALIASES
        extract_waterfalls = TestData.EXTRACT_WATERFALLS
        img_gen_presets = TestData.IMG_GEN_PRESETS
        img_gen_aliases = TestData.IMG_GEN_ALIASES
        img_gen_waterfalls = TestData.IMG_GEN_WATERFALLS
        search_presets = TestData.SEARCH_PRESETS
        search_aliases = TestData.SEARCH_ALIASES
        search_waterfalls = TestData.SEARCH_WATERFALLS

    return FakeModelDeck()


def _setup_mocks(mocker: MockerFixture) -> None:
    """Patch the common dependencies for agent_check_model_cmd."""
    mocker.patch(f"{MODULE_PATH}.make_pipelex_for_agent_cli")
    mocker.patch(f"{MODULE_PATH}.get_model_deck", return_value=_make_fake_model_deck())
    mocker.patch(f"{MODULE_PATH}.Pipelex")


def _run_check(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    name: str,
    model_type: ModelCategory = ModelCategory.LLM,
    output_format: CliOutputFormat = CliOutputFormat.JSON,
) -> dict[str, Any]:
    """Run check-model and return parsed JSON output."""
    _setup_mocks(mocker)
    agent_check_model_cmd(name=name, model_type=model_type, output_format=output_format)
    parsed: dict[str, Any] = json.loads(capsys.readouterr().out)
    return parsed


class TestCheckModelCmd:
    """Tests for agent_check_model_cmd validation and fuzzy matching."""

    def test_valid_preset(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A known preset name with $ sigil should be valid."""
        result = _run_check(mocker, capsys, "$writing-creative")
        assert result["valid"] is True
        assert result["kind"] == "preset"

    def test_valid_alias(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A known alias name with @ sigil should be valid."""
        result = _run_check(mocker, capsys, "@best-claude")
        assert result["valid"] is True
        assert result["kind"] == "alias"

    def test_valid_handle(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A known bare model handle should be valid."""
        result = _run_check(mocker, capsys, "claude-4.5-sonnet")
        assert result["valid"] is True
        assert result["kind"] == "handle"

    def test_invalid_preset_with_fuzzy_suggestions(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A typo in a preset name should return fuzzy suggestions with $ prefix."""
        result = _run_check(mocker, capsys, "$writting-creative")
        assert result["valid"] is False
        assert any("$writing-creative" in suggestion for suggestion in result["suggestions"])

    def test_wrong_sigil_detected(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Using $ for a name that exists as an alias should produce a wrong-sigil hint."""
        result = _run_check(mocker, capsys, "$best-claude")
        assert result["valid"] is False
        assert any("@best-claude" in hint for hint in result["wrong_sigil_hints"])

    def test_invalid_handle_cross_collection_suggestions(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A bare name matching a preset should suggest the prefixed version."""
        result = _run_check(mocker, capsys, "writing-creative")
        assert result["valid"] is False
        assert any("$writing-creative" in hint for hint in result["wrong_sigil_hints"])

    def test_invalid_handle_fuzzy_suggestions(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A typo in a handle should return fuzzy suggestions without sigil prefix."""
        result = _run_check(mocker, capsys, "claude-4.5-sonet")
        assert result["valid"] is False
        assert "claude-4.5-sonnet" in result["suggestions"]

    def test_completely_unknown_name(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A completely unknown name should return no suggestions."""
        result = _run_check(mocker, capsys, "$zzz-nonexistent-xyz")
        assert result["valid"] is False
        assert len(result["suggestions"]) == 0

    def test_json_output_structure(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output should contain all expected keys on failure."""
        result = _run_check(mocker, capsys, "$nonexistent")
        assert result["success"] is True
        assert result["valid"] is False
        assert "suggestions" in result
        assert "wrong_sigil_hints" in result
        assert "cross_collection_suggestions" in result
        assert result["model_type"] == "llm"

    def test_markdown_valid_output(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Markdown output for a valid reference should be a single confirmation line."""
        _setup_mocks(mocker)
        agent_check_model_cmd(name="$writing-creative", model_type=ModelCategory.LLM, output_format=CliOutputFormat.MARKDOWN)
        output = capsys.readouterr().out.strip()
        assert output == "$writing-creative is a valid llm preset."

    def test_markdown_invalid_output_has_suggestions(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Markdown output for an invalid reference should include 'Did you mean' suggestions."""
        _setup_mocks(mocker)
        agent_check_model_cmd(name="$writting-creative", model_type=ModelCategory.LLM, output_format=CliOutputFormat.MARKDOWN)
        output = capsys.readouterr().out
        assert "is not a valid" in output
        assert "Did you mean:" in output

    def test_valid_waterfall(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A known waterfall name with ~ sigil should be valid."""
        result = _run_check(mocker, capsys, "~robust-llm")
        assert result["valid"] is True
        assert result["kind"] == "waterfall"
