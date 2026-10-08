"""Unit tests for the agent CLI check-model command, against a real model deck."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.check_model_cmd import agent_check_model_cmd
from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_listing import CATEGORY_TO_MODEL_TYPE, ModelCategory
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction

MODULE_PATH = "pipelex.cli.agent_cli.commands.check_model_cmd"


def _model_spec(name: str, model_type: ModelType) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test_backend",
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=f"test_model_{name}",
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )


def _make_model_deck(*, is_model_fallback_enabled: bool = True) -> ModelDeck:
    """A deck with LLM presets, aliases and a waterfall, and one image-generation model."""
    return ModelDeck(
        inference_models={
            "claude-4.5-sonnet": _model_spec("claude-4.5-sonnet", ModelType.LLM),
            "claude-4-sonnet": _model_spec("claude-4-sonnet", ModelType.LLM),
            "claude-4.6-opus": _model_spec("claude-4.6-opus", ModelType.LLM),
            "gpt-4o": _model_spec("gpt-4o", ModelType.LLM),
            "gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM),
            "img-painter": _model_spec("img-painter", ModelType.IMG_GEN),
        },
        llm_default_temperature=0.7,
        llm_presets={
            "writing-creative": LLMSetting(model="claude-4.5-sonnet", temperature=0.9, description="Creative writing"),
            "writing-factual": LLMSetting(model="claude-4.5-sonnet", temperature=0.1, description="Factual writing"),
            "deep-analysis": LLMSetting(model="claude-4.6-opus", temperature=0.2, description="Deep analysis"),
        },
        llm_aliases={
            "best-claude": "claude-4.5-sonnet",
            "best-gpt": "gpt-4o",
            "default-general": "claude-4.5-sonnet",
        },
        llm_waterfalls={"robust-llm": ["claude-4.5-sonnet", "gpt-4o"]},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="claude-4.5-sonnet", temperature=0.7),
            for_object=LLMSetting(model="claude-4.5-sonnet", temperature=0.1),
        ),
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_choice_default="img-painter",
        search_choice_default="web-searcher",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=is_model_fallback_enabled, missing_presets_reaction=ProblemReaction.NONE),
    )


def _setup_mocks(mocker: MockerFixture, *, model_deck: ModelDeck) -> None:
    """Patch the boot and the deck accessor of agent_check_model_cmd."""
    mocker.patch(f"{MODULE_PATH}.make_pipelex_for_agent_cli")
    mocker.patch(f"{MODULE_PATH}.get_model_deck", return_value=model_deck)
    mocker.patch(f"{MODULE_PATH}.Pipelex")


def _run_check(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    name: str,
    model_type: ModelCategory = ModelCategory.LLM,
    *,
    model_deck: ModelDeck | None = None,
) -> dict[str, Any]:
    """Run check-model and return its parsed JSON output."""
    _setup_mocks(mocker, model_deck=model_deck or _make_model_deck())
    agent_check_model_cmd(name=name, model_type=model_type, output_format=CliOutputFormat.JSON)
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

    def test_valid_waterfall(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A known waterfall name with ~ sigil should be valid."""
        result = _run_check(mocker, capsys, "~robust-llm")
        assert result["valid"] is True
        assert result["kind"] == "waterfall"

    def test_bare_alias_name_is_a_valid_handle(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A bare name the type's aliases hold is a handle a pipe resolves, so it is valid, as a validation accepts it."""
        result = _run_check(mocker, capsys, "best-claude")
        assert result["valid"] is True
        assert result["kind"] == "handle"

    @pytest.mark.parametrize(
        ("is_model_fallback_enabled", "expected_valid"),
        [
            (True, True),
            (False, False),
        ],
    )
    def test_bare_waterfall_name_is_valid_while_fallback_is_on(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        is_model_fallback_enabled: bool,
        expected_valid: bool,
    ) -> None:
        """A bare name the type's waterfalls hold is a handle while model fallback is on."""
        model_deck = _make_model_deck(is_model_fallback_enabled=is_model_fallback_enabled)
        result = _run_check(mocker, capsys, "robust-llm", model_deck=model_deck)
        assert result["valid"] is expected_valid

    def test_handle_served_as_another_type_is_not_valid(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A model the deck serves as an LLM is not a valid image-generation handle."""
        result = _run_check(mocker, capsys, "gpt-4o", ModelCategory.IMG_GEN)
        assert result["valid"] is False
        assert result["model_type"] == "img_gen"

    @pytest.mark.parametrize(
        "name",
        [
            "$writing-creative",
            "@best-gpt",
            "~robust-llm",
            "claude-4.5-sonnet",
            "img-painter",
            "best-claude",
            "robust-llm",
            "writing-creative",
            "alias:best-gpt",
            "handle:gpt-4o",
            "$best-claude",
            "@held-nowhere",
        ],
    )
    @pytest.mark.parametrize("model_type", list(ModelCategory))
    def test_verdict_agrees_with_the_deck(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        name: str,
        model_type: ModelCategory,
    ) -> None:
        """The command answers as `ModelDeck.is_reference_defined`, the rule a validation and the reference check apply."""
        model_deck = _make_model_deck()
        result = _run_check(mocker, capsys, name, model_type, model_deck=model_deck)
        expected = model_deck.is_reference_defined(reference=ModelReference.parse(name), model_type=CATEGORY_TO_MODEL_TYPE[model_type])
        assert result["valid"] is expected

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

    def test_bare_preset_name_is_not_a_handle(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A bare name matching only a preset is not a handle, and the hint names the prefixed preset."""
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
        _setup_mocks(mocker, model_deck=_make_model_deck())
        agent_check_model_cmd(name="$writing-creative", model_type=ModelCategory.LLM, output_format=CliOutputFormat.MARKDOWN)
        output = capsys.readouterr().out.strip()
        assert output == "$writing-creative is a valid llm preset."

    def test_markdown_invalid_output_has_suggestions(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Markdown output for an invalid reference should include 'Did you mean' suggestions."""
        _setup_mocks(mocker, model_deck=_make_model_deck())
        agent_check_model_cmd(name="$writting-creative", model_type=ModelCategory.LLM, output_format=CliOutputFormat.MARKDOWN)
        output = capsys.readouterr().out
        assert "is not a valid" in output
        assert "Did you mean:" in output
