import pytest
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import pretty_print
from pipelex.plugin.mistral.mistral_llms import list_mistral_models


# make t VERBOSE=2 TEST=TestMistral
@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
class TestMistral:
    # pytest -k test_mistral_list_models -s -vv
    # make t VERBOSE=2 TEST=test_mistral_list_models
    def test_mistral_list_models(self, pytestconfig: pytest.Config):
        mistral_models_list = list_mistral_models()
        if pytestconfig.get_verbosity() >= 2:
            # Create and configure the table
            console = Console()
            table = Table(
                title="Available Mistral Models",
                show_header=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
            )

            # Add columns
            table.add_column("LLM ID", style="green")
            table.add_column("Max Context Length", style="yellow")

            # Add rows
            for model in mistral_models_list:
                if max_context_length := model.max_context_length:
                    table.add_row(model.id, str(max_context_length))

            # Print the table
            console.print("\n")
            console.print(table)
            console.print("\n")

    # pytest -k test_mistral_list_model_ids -s -vv
    # make t VERBOSE=2 TEST=test_mistral_list_model_ids
    def test_mistral_list_model_ids(self, pytestconfig: pytest.Config):
        mistral_models_list = list_mistral_models()
        mistral_model_ids = [{"id": model.id, "aliases": model.aliases} for model in mistral_models_list]
        if pytestconfig.get_verbosity() >= 2:
            pretty_print(mistral_model_ids)
