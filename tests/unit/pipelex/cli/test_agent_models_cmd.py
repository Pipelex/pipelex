"""Unit tests for the agent CLI models command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

from pipelex.builder.operations.models_ops import ModelCategory
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.models_cmd import agent_models_cmd
from pipelex.cogt.model_backends.model_type import ModelType

CMD_MODULE_PATH = "pipelex.cli.agent_cli.commands.models_cmd"
OPS_MODULE_PATH = "pipelex.builder.operations.models_ops"


class _FakeSetting:
    """Minimal stand-in for LLMSetting / ExtractSetting / ImgGenSetting."""

    def __init__(self, model: str, description: str | None = None):
        self.model = model
        self.description = description


class _FakeInferenceModelSpec:
    """Minimal stand-in for InferenceModelSpec."""

    def __init__(self, backend_name: str, model_type: ModelType):
        self.backend_name = backend_name
        self.model_type = model_type


class TestData:
    """Shared test data constants."""

    LLM_PRESETS: ClassVar[dict[str, _FakeSetting]] = {
        "fast": _FakeSetting(model="gpt-4o-mini", description="Fast LLM"),
        "smart": _FakeSetting(model="claude-sonnet", description="Smart LLM"),
    }
    EXTRACT_PRESETS: ClassVar[dict[str, _FakeSetting]] = {
        "doc-extract": _FakeSetting(model="textract-model", description="Doc extraction"),
    }
    IMG_GEN_PRESETS: ClassVar[dict[str, _FakeSetting]] = {
        "hd-image": _FakeSetting(model="dall-e-3", description="HD images"),
    }

    LLM_ALIASES: ClassVar[dict[str, str]] = {"best-llm": "claude-sonnet"}
    EXTRACT_ALIASES: ClassVar[dict[str, str]] = {"best-extract": "textract-model"}
    IMG_GEN_ALIASES: ClassVar[dict[str, str]] = {"best-img": "dall-e-3"}

    LLM_WATERFALLS: ClassVar[dict[str, list[str]]] = {"llm-wf": ["claude-sonnet", "gpt-4o-mini"]}
    EXTRACT_WATERFALLS: ClassVar[dict[str, list[str]]] = {"extract-wf": ["textract-model"]}
    IMG_GEN_WATERFALLS: ClassVar[dict[str, list[str]]] = {"img-wf": ["dall-e-3"]}

    INFERENCE_MAP: ClassVar[dict[str, tuple[str, ModelType]]] = {
        "gpt-4o-mini": ("openai", ModelType.LLM),
        "claude-sonnet": ("anthropic", ModelType.LLM),
        "textract-model": ("aws", ModelType.TEXT_EXTRACTOR),
        "dall-e-3": ("openai", ModelType.IMG_GEN),
    }


def _make_fake_model_deck() -> Any:
    """Create a fake ModelDeck with all test data."""

    class FakeModelDeck:
        llm_presets = TestData.LLM_PRESETS
        extract_presets = TestData.EXTRACT_PRESETS
        img_gen_presets = TestData.IMG_GEN_PRESETS
        search_presets: ClassVar[dict[str, Any]] = {}

        llm_aliases = TestData.LLM_ALIASES
        extract_aliases = TestData.EXTRACT_ALIASES
        img_gen_aliases = TestData.IMG_GEN_ALIASES
        search_aliases: ClassVar[dict[str, str]] = {}

        llm_waterfalls = TestData.LLM_WATERFALLS
        extract_waterfalls = TestData.EXTRACT_WATERFALLS
        img_gen_waterfalls = TestData.IMG_GEN_WATERFALLS
        search_waterfalls: ClassVar[dict[str, list[str]]] = {}

        def get_optional_inference_model(self, model_handle: str, model_type: ModelType) -> _FakeInferenceModelSpec | None:
            entry = TestData.INFERENCE_MAP.get(model_handle)
            if entry is None:
                return None
            backend_name, spec_model_type = entry
            if spec_model_type != model_type:
                return None
            return _FakeInferenceModelSpec(backend_name=backend_name, model_type=spec_model_type)

    return FakeModelDeck()


def _setup_mocks(mocker: MockerFixture) -> None:
    """Patch the common dependencies for agent_models_cmd."""
    mocker.patch(f"{CMD_MODULE_PATH}.make_pipelex_for_agent_cli")
    mocker.patch(f"{OPS_MODULE_PATH}.get_model_deck", return_value=_make_fake_model_deck())
    mocker.patch(f"{CMD_MODULE_PATH}.Pipelex")


class TestAgentModelsCmd:
    """Tests for agent_models_cmd JSON output with --type and --backend filters."""

    def test_no_filters_returns_all_categories(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """No filters should return all categories in every section."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        for section in ("presets", "aliases", "waterfalls"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "extract" in parsed[section], f"extract missing from {section}"

    def test_no_talent_mappings_in_output(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Output should not contain talent_mappings or usage hint."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert "talent_mappings" not in parsed
        assert "talent_mappings_usage_hint" not in parsed

    def test_no_filters_preset_content(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """No filters should include all preset entries with correct data."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" in llm_preset_names
        fast_preset = next(preset for preset in parsed["presets"]["llm"] if preset["name"] == "fast")
        assert fast_preset["description"] == "Fast LLM"

    def test_type_llm_only(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm should return only llm keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.LLM], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" not in parsed[section], f"img_gen should not be in {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_type_extract_only(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type extract should return only extract keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.EXTRACT], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "extract" in parsed[section], f"extract missing from {section}"
            assert "llm" not in parsed[section], f"llm should not be in {section}"
            assert "img_gen" not in parsed[section], f"img_gen should not be in {section}"

    def test_type_img_gen_only(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type img_gen should return only img_gen keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.IMG_GEN], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "llm" not in parsed[section], f"llm should not be in {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_type_llm_and_img_gen(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm --type img_gen should return both llm and img_gen, but not extract."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.LLM, ModelCategory.IMG_GEN], output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_backend_filter_openai(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend openai should filter presets/aliases/waterfalls to only openai-backed models."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="openai", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" not in llm_preset_names
        assert len(parsed["aliases"]["llm"]) == 0
        img_gen_preset_names = [preset["name"] for preset in parsed["presets"]["img_gen"]]
        assert "hd-image" in img_gen_preset_names
        assert len(parsed["presets"]["extract"]) == 0

    def test_backend_filter_anthropic(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend anthropic should include only anthropic-backed models."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="anthropic", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "smart" in llm_preset_names
        assert "fast" not in llm_preset_names
        assert "best-llm" in parsed["aliases"]["llm"]

    def test_type_and_backend_combined(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm --backend openai should combine both filters."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.LLM], backend="openai", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert "llm" in parsed["presets"]
        assert "img_gen" not in parsed["presets"]
        assert "extract" not in parsed["presets"]
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" not in llm_preset_names

    def test_backend_nonexistent(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend nonexistent should produce empty presets/aliases/waterfalls."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="nonexistent", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        for section in ("presets", "aliases", "waterfalls"):
            for category in ("llm", "img_gen", "extract"):
                assert len(parsed[section][category]) == 0, f"{section}.{category} should be empty"

    def test_waterfalls_backend_filter(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend anthropic should include llm waterfall (has claude-sonnet) but not img waterfall."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="anthropic", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert "llm-wf" in parsed["waterfalls"]["llm"]
        assert len(parsed["waterfalls"]["img_gen"]) == 0
        assert len(parsed["waterfalls"]["extract"]) == 0
