"""Unit tests for the agent CLI models command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.models_cmd import agent_models_cmd
from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_listing import ModelCategory
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction

CMD_MODULE_PATH = "pipelex.cli.agent_cli.commands.models_cmd"
OPS_MODULE_PATH = "pipelex.cogt.models.model_listing"


class TestData:
    """Shared test data constants."""

    LLM_PRESETS: ClassVar[dict[str, LLMSetting]] = {
        "fast": LLMSetting(model="gpt-4o-mini", temperature=0.5, description="Fast LLM"),
        "smart": LLMSetting(model="claude-sonnet", temperature=0.5, description="Smart LLM"),
    }
    EXTRACT_PRESETS: ClassVar[dict[str, ExtractSetting]] = {
        "doc-extract": ExtractSetting(model="textract-model", description="Doc extraction"),
    }
    IMG_GEN_PRESETS: ClassVar[dict[str, ImgGenSetting]] = {
        "hd-image": ImgGenSetting(model="dall-e-3", description="HD images"),
    }

    LLM_ALIASES: ClassVar[dict[str, str]] = {"best-llm": "claude-sonnet"}
    EXTRACT_ALIASES: ClassVar[dict[str, str]] = {"best-extract": "textract-model"}
    IMG_GEN_ALIASES: ClassVar[dict[str, str]] = {"best-img": "dall-e-3"}

    LLM_WATERFALLS: ClassVar[dict[str, list[str]]] = {"llm-wf": ["claude-sonnet", "gpt-4o-mini"]}
    EXTRACT_WATERFALLS: ClassVar[dict[str, list[str]]] = {"extract-wf": ["textract-model"]}
    IMG_GEN_WATERFALLS: ClassVar[dict[str, list[str]]] = {"img-wf": ["dall-e-3"]}

    # The models the deck serves: handle -> (backend, model type).
    INFERENCE_MAP: ClassVar[dict[str, tuple[str, ModelType]]] = {
        "gpt-4o-mini": ("openai", ModelType.LLM),
        "claude-sonnet": ("anthropic", ModelType.LLM),
        "textract-model": ("aws", ModelType.TEXT_EXTRACTOR),
        "dall-e-3": ("openai", ModelType.IMG_GEN),
    }


def _model_spec(*, name: str, backend_name: str, model_type: ModelType) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=name,
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )


def _make_model_deck(
    *,
    llm_aliases: dict[str, str] | None = None,
    llm_waterfalls: dict[str, list[str]] | None = None,
) -> ModelDeck:
    """A real model deck serving the test data's models, with its presets, aliases and waterfalls."""
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(
            model_specs=[
                _model_spec(name=name, backend_name=backend_name, model_type=model_type)
                for name, (backend_name, model_type) in TestData.INFERENCE_MAP.items()
            ]
        ),
        llm_default_temperature=0.7,
        llm_presets=TestData.LLM_PRESETS,
        llm_aliases=TestData.LLM_ALIASES if llm_aliases is None else llm_aliases,
        llm_waterfalls=TestData.LLM_WATERFALLS if llm_waterfalls is None else llm_waterfalls,
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_presets=TestData.EXTRACT_PRESETS,
        extract_aliases=TestData.EXTRACT_ALIASES,
        extract_waterfalls=TestData.EXTRACT_WATERFALLS,
        extract_choice_default="textract-model",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_presets=TestData.IMG_GEN_PRESETS,
        img_gen_aliases=TestData.IMG_GEN_ALIASES,
        img_gen_waterfalls=TestData.IMG_GEN_WATERFALLS,
        img_gen_choice_default="dall-e-3",
        search_choice_default="@default-search",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _setup_mocks(mocker: MockerFixture, *, model_deck: ModelDeck | None = None) -> None:
    """Patch the common dependencies for agent_models_cmd."""
    mocker.patch(f"{CMD_MODULE_PATH}.make_pipelex_for_agent_cli")
    mocker.patch(f"{OPS_MODULE_PATH}.get_model_deck", return_value=model_deck or _make_model_deck())
    mocker.patch(f"{CMD_MODULE_PATH}.Pipelex")


class TestAgentModelsCmd:
    """Tests for agent_models_cmd JSON output with --type and --backend filters."""

    def test_no_filters_returns_all_categories(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """No filters should return all categories in every section."""
        _setup_mocks(mocker)

        agent_models_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        for section in ("presets", "aliases", "waterfalls"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "extract" in parsed[section], f"extract missing from {section}"

    def test_no_talent_mappings_in_output(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Output should not contain talent_mappings or usage hint."""
        _setup_mocks(mocker)

        agent_models_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert "talent_mappings" not in parsed
        assert "talent_mappings_usage_hint" not in parsed

    def test_no_filters_preset_content(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """No filters should include all preset entries with correct data."""
        _setup_mocks(mocker)

        agent_models_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" in llm_preset_names
        fast_preset = next(preset for preset in parsed["presets"]["llm"] if preset["name"] == "fast")
        assert fast_preset["description"] == "Fast LLM"

    def test_type_llm_only(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm should return only llm keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(model_type=[ModelCategory.LLM], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" not in parsed[section], f"img_gen should not be in {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_type_extract_only(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type extract should return only extract keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(model_type=[ModelCategory.EXTRACT], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "extract" in parsed[section], f"extract missing from {section}"
            assert "llm" not in parsed[section], f"llm should not be in {section}"
            assert "img_gen" not in parsed[section], f"img_gen should not be in {section}"

    def test_type_img_gen_only(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type img_gen should return only img_gen keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(model_type=[ModelCategory.IMG_GEN], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "llm" not in parsed[section], f"llm should not be in {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_type_llm_and_img_gen(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm --type img_gen should return both llm and img_gen, but not extract."""
        _setup_mocks(mocker)

        agent_models_cmd(model_type=[ModelCategory.LLM, ModelCategory.IMG_GEN], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_backend_filter_openai(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend openai should filter presets/aliases/waterfalls to only openai-backed models."""
        _setup_mocks(mocker)

        agent_models_cmd(backend="openai", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" not in llm_preset_names
        assert len(parsed["aliases"]["llm"]) == 0
        img_gen_preset_names = [preset["name"] for preset in parsed["presets"]["img_gen"]]
        assert "hd-image" in img_gen_preset_names
        assert len(parsed["presets"]["extract"]) == 0

    def test_backend_filter_anthropic(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend anthropic should include only anthropic-backed models."""
        _setup_mocks(mocker)

        agent_models_cmd(backend="anthropic", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "smart" in llm_preset_names
        assert "fast" not in llm_preset_names
        assert "best-llm" in parsed["aliases"]["llm"]

    def test_type_and_backend_combined(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm --backend openai should combine both filters."""
        _setup_mocks(mocker)

        agent_models_cmd(model_type=[ModelCategory.LLM], backend="openai", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert "llm" in parsed["presets"]
        assert "img_gen" not in parsed["presets"]
        assert "extract" not in parsed["presets"]
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" not in llm_preset_names

    def test_backend_nonexistent(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend nonexistent should produce empty presets/aliases/waterfalls."""
        _setup_mocks(mocker)

        agent_models_cmd(backend="nonexistent", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        for section in ("presets", "aliases", "waterfalls"):
            for category in ("llm", "img_gen", "extract"):
                assert len(parsed[section][category]) == 0, f"{section}.{category} should be empty"

    def test_waterfalls_backend_filter(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend anthropic should include llm waterfall (has claude-sonnet) but not img waterfall."""
        _setup_mocks(mocker)

        agent_models_cmd(backend="anthropic", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert "llm-wf" in parsed["waterfalls"]["llm"]
        assert len(parsed["waterfalls"]["img_gen"]) == 0
        assert len(parsed["waterfalls"]["extract"]) == 0

    def test_backend_filter_skips_an_alias_whose_waterfall_no_backend_serves(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """An alias bound to a waterfall none of whose models is served resolves on no backend, rather than failing the listing."""
        model_deck = _make_model_deck(
            llm_aliases={"robust": "~unserved", "best-gpt": "gpt-4o-mini"},
            llm_waterfalls={"unserved": ["gpt-9", "gpt-10"]},
        )
        _setup_mocks(mocker, model_deck=model_deck)

        agent_models_cmd(backend="openai", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["aliases"]["llm"] == {"best-gpt": "gpt-4o-mini"}
