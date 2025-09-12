import pytest
from anthropic import AuthenticationError
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex.cogt.exceptions import LLMSDKError
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.plugins.anthropic.anthropic_llms import anthropic_list_anthropic_models


# TODO: fix this: test works for Anthropic but not if you set peferred platform for Anthropic is Bedrock
# make t VERBOSE=2 TEST=TestAnthropic
@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
@pytest.mark.asyncio(loop_scope="class")
class TestAnthropic:
    # pytest -k test_anthropic_list_models -s -vv
    # make t VERBOSE=2 TEST=test_anthropic_list_models
    async def test_anthropic_list_models(
        self,
        pytestconfig: pytest.Config,
        llm_platform_for_anthropic_sdk: LLMPlatform,
    ):
        try:
            anthropic_models_list = await anthropic_list_anthropic_models(llm_platform=llm_platform_for_anthropic_sdk)
        except AuthenticationError as auth_exc:
            pytest.fail(f"Authentication error for Anthropic: {auth_exc}")
        except LLMSDKError as exc:
            if "does not support listing models" in str(exc):
                pytest.skip(f"Skipping: {exc}")
            else:
                pytest.fail(f"Error listing Anthropic models: {exc}")
        if pytestconfig.get_verbosity() >= 2:
            # Create and configure the table
            console = Console()
            table = Table(
                title="Available Anthropic Models",
                show_header=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
            )

            # Add columns
            table.add_column("Model ID", style="green")
            table.add_column("Display Name", style="blue")
            table.add_column("Created At", style="yellow")

            # Add rows
            for model in anthropic_models_list:
                # Format the date as YYYY-MM-DD
                created_date = model.created_at.strftime("%Y-%m-%d") if model.created_at else "N/A"
                table.add_row(model.id, model.display_name, created_date)

            # Print the table
            console.print("\n")
            console.print(table)
            console.print("\n")
