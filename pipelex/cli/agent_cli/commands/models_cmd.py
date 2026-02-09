"""Agent CLI models command -- list available model presets, aliases, and talent mappings."""

from typing import Any

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.config import get_config
from pipelex.hub import get_model_deck
from pipelex.pipelex import Pipelex


def agent_models_cmd() -> None:
    """List available model presets, aliases, waterfalls, and talent mappings.

    Outputs structured JSON to stdout with all model configuration
    that an agent needs to reference when building pipelines.
    """
    try:
        make_pipelex_for_agent_cli()

        model_deck = get_model_deck()
        builder_config = get_config().pipelex.builder_config
        talent_mappings = builder_config.talent_preset_mappings

        # LLM presets
        llm_presets: list[dict[str, Any]] = []
        for preset_name, llm_setting in model_deck.llm_presets.items():
            llm_entry: dict[str, Any] = {"name": preset_name}
            if llm_setting.description is not None:
                llm_entry["description"] = llm_setting.description
            llm_presets.append(llm_entry)

        # ImgGen presets
        img_gen_presets: list[dict[str, Any]] = []
        for preset_name, img_gen_setting in model_deck.img_gen_presets.items():
            img_gen_entry: dict[str, Any] = {"name": preset_name}
            if img_gen_setting.description is not None:
                img_gen_entry["description"] = img_gen_setting.description
            img_gen_presets.append(img_gen_entry)

        # Extract presets
        extract_presets: list[dict[str, Any]] = []
        for preset_name, extract_setting in model_deck.extract_presets.items():
            extract_entry: dict[str, Any] = {"name": preset_name}
            if extract_setting.description is not None:
                extract_entry["description"] = extract_setting.description
            extract_presets.append(extract_entry)

        result: dict[str, Any] = {
            "success": True,
            "presets": {
                "llm": llm_presets,
                "img_gen": img_gen_presets,
                "extract": extract_presets,
            },
            "aliases": {
                "llm": model_deck.llm_aliases,
                "img_gen": model_deck.img_gen_aliases,
                "extract": model_deck.extract_aliases,
            },
            "waterfalls": {
                "llm": model_deck.llm_waterfalls,
                "img_gen": model_deck.img_gen_waterfalls,
                "extract": model_deck.extract_waterfalls,
            },
            "talent_mappings": {
                "llm": talent_mappings.llm,
                "img_gen": talent_mappings.img_gen,
                "extract": talent_mappings.extract,
            },
        }

        agent_success(result)
    except SystemExit:
        # agent_error already handled and called sys.exit
        raise
    except Exception as exc:
        agent_error(f"Failed to list models: {exc}", type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
