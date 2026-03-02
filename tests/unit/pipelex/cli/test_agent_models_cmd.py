"""Unit tests for the agent CLI models command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.models_cmd import ModelCategory, agent_models_cmd
from pipelex.cogt.model_backends.model_type import ModelType

MODULE_PATH = "pipelex.cli.agent_cli.commands.models_cmd"


class _FakeSetting:
    """Minimal stand-in for LLMSetting / ExtractSetting / ImgGenSetting."""

    def __init__(self, model: str, description: str | None = None):
        self.model = model
        self.description = description


class _FakeTalentMappings:
    """Minimal stand-in for TalentPresetMappings."""

    def __init__(self, llm: dict[str, str], img_gen: dict[str, str], extract: dict[str, str], search: dict[str, str] | None = None):
        self.llm = llm
        self.img_gen = img_gen
        self.extract = extract
        self.search = search or {}


class _FakeBuilderConfig:
    def __init__(self, talent_preset_mappings: _FakeTalentMappings):
        self.talent_preset_mappings = talent_preset_mappings


class _FakePipelexConfig:
    def __init__(self, builder_config: _FakeBuilderConfig):
        self.builder_config = builder_config


class _FakeConfig:
    def __init__(self, pipelex: _FakePipelexConfig):
        self.pipelex = pipelex


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

    TALENT_LLM: ClassVar[dict[str, str]] = {"text_gen": "fast"}
    TALENT_IMG_GEN: ClassVar[dict[str, str]] = {"image_gen": "hd-image"}
    TALENT_EXTRACT: ClassVar[dict[str, str]] = {"extraction": "doc-extract"}

    # Backend resolution map: model_handle -> (backend_name, model_type)
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


def _make_fake_config() -> _FakeConfig:
    """Create a fake config with talent mappings."""
    talent_mappings = _FakeTalentMappings(
        llm=TestData.TALENT_LLM,
        img_gen=TestData.TALENT_IMG_GEN,
        extract=TestData.TALENT_EXTRACT,
    )
    return _FakeConfig(
        pipelex=_FakePipelexConfig(
            builder_config=_FakeBuilderConfig(talent_preset_mappings=talent_mappings),
        ),
    )


def _setup_mocks(mocker: MockerFixture) -> None:
    """Patch the common dependencies for agent_models_cmd."""
    mocker.patch(f"{MODULE_PATH}.make_pipelex_for_agent_cli")
    mocker.patch(f"{MODULE_PATH}.get_model_deck", return_value=_make_fake_model_deck())
    mocker.patch(f"{MODULE_PATH}.get_config", return_value=_make_fake_config())
    mocker.patch(f"{MODULE_PATH}.Pipelex")


class TestAgentModelsCmd:
    """Tests for agent_models_cmd JSON output with --type and --backend filters."""

    def test_no_filters_returns_all_categories(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """No filters should return all 3 categories in every section."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        for section in ("presets", "aliases", "waterfalls", "talent_mappings"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "extract" in parsed[section], f"extract missing from {section}"

    def test_no_filters_preset_content(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """No filters should include all preset entries with correct data."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx)

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" in llm_preset_names
        # Check description is included
        fast_preset = next(preset for preset in parsed["presets"]["llm"] if preset["name"] == "fast")
        assert fast_preset["description"] == "Fast LLM"

    def test_type_llm_only(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm should return only llm keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.LLM])

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls", "talent_mappings"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" not in parsed[section], f"img_gen should not be in {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_type_extract_only(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type extract should return only extract keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.EXTRACT])

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls", "talent_mappings"):
            assert "extract" in parsed[section], f"extract missing from {section}"
            assert "llm" not in parsed[section], f"llm should not be in {section}"
            assert "img_gen" not in parsed[section], f"img_gen should not be in {section}"

    def test_type_img_gen_only(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type img_gen should return only img_gen keys in all sections."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.IMG_GEN])

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls", "talent_mappings"):
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "llm" not in parsed[section], f"llm should not be in {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_type_llm_and_img_gen(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm --type img_gen should return both llm and img_gen, but not extract."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.LLM, ModelCategory.IMG_GEN])

        parsed = json.loads(capsys.readouterr().out)
        for section in ("presets", "aliases", "waterfalls", "talent_mappings"):
            assert "llm" in parsed[section], f"llm missing from {section}"
            assert "img_gen" in parsed[section], f"img_gen missing from {section}"
            assert "extract" not in parsed[section], f"extract should not be in {section}"

    def test_backend_filter_openai(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend openai should filter presets/aliases/waterfalls to only openai-backed models."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="openai")

        parsed = json.loads(capsys.readouterr().out)
        # LLM: only 'fast' preset (gpt-4o-mini on openai), not 'smart' (claude-sonnet on anthropic)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" not in llm_preset_names
        # LLM aliases: best-llm -> claude-sonnet (anthropic), should be excluded
        assert len(parsed["aliases"]["llm"]) == 0
        # IMG_GEN: dall-e-3 is on openai, should be included
        img_gen_preset_names = [preset["name"] for preset in parsed["presets"]["img_gen"]]
        assert "hd-image" in img_gen_preset_names
        # Extract: textract-model is on aws, should be excluded
        assert len(parsed["presets"]["extract"]) == 0

    def test_backend_filter_anthropic(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend anthropic should include only anthropic-backed models."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="anthropic")

        parsed = json.loads(capsys.readouterr().out)
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "smart" in llm_preset_names
        assert "fast" not in llm_preset_names
        # Alias best-llm -> claude-sonnet (anthropic) should be included
        assert "best-llm" in parsed["aliases"]["llm"]

    def test_type_and_backend_combined(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--type llm --backend openai should combine both filters."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, model_type=[ModelCategory.LLM], backend="openai")

        parsed = json.loads(capsys.readouterr().out)
        # Only llm category
        assert "llm" in parsed["presets"]
        assert "img_gen" not in parsed["presets"]
        assert "extract" not in parsed["presets"]
        # Only openai-backed LLM presets
        llm_preset_names = [preset["name"] for preset in parsed["presets"]["llm"]]
        assert "fast" in llm_preset_names
        assert "smart" not in llm_preset_names

    def test_backend_nonexistent(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend nonexistent should produce empty presets/aliases/waterfalls/talent_mappings."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="nonexistent")

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        for section in ("presets", "aliases", "waterfalls", "talent_mappings"):
            for category in ("llm", "img_gen", "extract"):
                assert len(parsed[section][category]) == 0, f"{section}.{category} should be empty"

    def test_waterfalls_backend_filter(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend anthropic should include llm waterfall (has claude-sonnet) but not img waterfall."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="anthropic")

        parsed = json.loads(capsys.readouterr().out)
        assert "llm-wf" in parsed["waterfalls"]["llm"]
        assert len(parsed["waterfalls"]["img_gen"]) == 0
        assert len(parsed["waterfalls"]["extract"]) == 0

    def test_talent_mappings_backend_filter(self, agent_ctx: Any, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--backend openai should include LLM talent_mapping (fast->gpt-4o-mini) and img_gen, but not extract."""
        _setup_mocks(mocker)

        agent_models_cmd(ctx=agent_ctx, backend="openai")

        parsed = json.loads(capsys.readouterr().out)
        assert "text_gen" in parsed["talent_mappings"]["llm"]
        assert "image_gen" in parsed["talent_mappings"]["img_gen"]
        assert len(parsed["talent_mappings"]["extract"]) == 0
