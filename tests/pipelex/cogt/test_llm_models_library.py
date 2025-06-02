from typing import List, Optional

import pytest
from rich import box
from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_engine_factory import LLMEngineFactory
from pipelex.cogt.llm.llm_models.llm_model import LLMModel
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform, LLMPlatformChoice
from pipelex.hub import get_llm_models_provider


def print_models(models: List[LLMModel], title: Optional[str] = None):
    console = Console()
    table = Table(
        title=title,
        show_header=True,
        show_lines=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Creator")
    table.add_column("Family")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Default platform")
    table.add_column("Platform ids")

    sorted_models = sorted(models, key=lambda m: (m.llm_family, m.llm_name, m.version))
    for model in sorted_models:
        platform_elemnts: List[RenderableType] = []
        for platform, llm_id in model.platform_llm_id.items():
            text = Text.assemble((platform, platform.console_color), f" - {llm_id}")
            if platform != list(model.platform_llm_id.keys())[-1]:
                ready = Padding(text, (0, 0, 1, 0))
            else:
                ready = Padding(text, (0, 0, 0, 0))
            platform_elemnts.append(ready)
        platforms = Group(*platform_elemnts)

        table.add_row(
            Text(model.llm_family.creator, model.llm_family.creator.console_color),
            model.llm_family,
            model.llm_name,
            model.version,
            model.default_platform,
            platforms,
        )
    console.print("\n")
    console.print(table)


class TestLLMModelsDB:
    def test_llm_models_loading(self, pytestconfig: pytest.Config):
        all_llm_models = get_llm_models_provider().get_all_llm_models()
        if pytestconfig.get_verbosity() >= 2:
            print_models(models=all_llm_models, title="All available LLM Models (unit testing)")
        assert len(all_llm_models) > 0, "No LLM models found"
        assert all(isinstance(model, LLMModel) for model in all_llm_models), "Invalid model type found"
        for llm_model in all_llm_models:
            log.debug(f"Checking model: {llm_model.name_and_version}")
            assert llm_model.llm_name, "Missing llm_name"
            assert llm_model.version, "Missing version"
            assert llm_model.llm_family, "Missing llm_family"
            assert llm_model.default_platform, "Missing default_platform"
            assert llm_model.platform_llm_id, "Missing platform_llm_id"

    @pytest.mark.parametrize(
        "llm_name, llm_version, llm_platform_choice",
        [
            # ("mistral-large", "latest", "default"),
            # ("mistral-large", "latest", LLMPlatform.BEDROCK_MISTRAL),
            # ("mistral-large", "latest", LLMPlatform.MISTRAL),
            # ("gpt-4o", "2024-08-06", "default"),
            ("gpt-4o", "2024-08-06", LLMPlatform.OPENAI),
            # ("gpt-4.1-mini", "latest", LLMPlatform.OPENAI),
            # ("gpt-4o-mini", "latest", LLMPlatform.ANTHROPIC),
            # ("gpt-4o-mini", "latest", LLMPlatform.BEDROCK_ANTHROPIC),
            # ("gpt-4o-mini", "latest", LLMPlatform.AZURE_OPENAI),
            # ("gpt-4o-mini", "latest", LLMPlatform.MISTRAL),
        ],
    )
    def test_get_llm_model(
        self,
        llm_name: str,
        llm_version: str,
        llm_platform_choice: LLMPlatformChoice,
    ):
        model = get_llm_models_provider().get_llm_model(llm_name=llm_name, llm_version=llm_version, llm_platform_choice=llm_platform_choice)
        pretty_print(model)
        assert isinstance(model, LLMModel)
        assert model.llm_name == llm_name
        if llm_version != "latest":
            assert model.version == llm_version
        if llm_platform_choice == "default":
            assert model.default_platform in model.platform_llm_id
        else:
            llm_platform = llm_platform_choice
            assert llm_platform in model.platform_llm_id

    @pytest.mark.parametrize(
        "llm_name, llm_version, llm_platform_choice",
        [
            # ("mistral-large", "latest", "default"),
            # ("mistral-large", "latest", LLMPlatform.BEDROCK_MISTRAL),
            # ("mistral-large", "latest", LLMPlatform.MISTRAL),
            # ("gpt-4o", "2024-08-06", "default"),
            ("gpt-4o", "2024-08-06", LLMPlatform.OPENAI),
            # ("gpt-4o-mini", "latest", LLMPlatform.ANTHROPIC),
            # ("gpt-4o-mini", "latest", LLMPlatform.BEDROCK_ANTHROPIC),
            # ("gpt-4o-mini", "latest", LLMPlatform.AZURE_OPENAI),
            # ("gpt-4o-mini", "latest", LLMPlatform.MISTRAL),
        ],
    )
    def test_make_llm_engine(
        self,
        llm_name: str,
        llm_version: str,
        llm_platform_choice: LLMPlatformChoice,
    ):
        engine_card: LLMEngineBlueprint = LLMEngineBlueprint(
            llm_name=llm_name,
            llm_version=llm_version,
            llm_platform_choice=llm_platform_choice,
        )
        engine = LLMEngineFactory.make_llm_engine(engine_card)
        pretty_print(engine)

        assert engine is not None
        assert isinstance(engine, LLMEngine)
        assert engine.llm_model.llm_name == llm_name
        assert engine.llm_model.version == llm_version
