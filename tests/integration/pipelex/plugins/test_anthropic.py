import pytest
from anthropic import AuthenticationError
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex.hub import get_models_manager
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicSDKUnsupportedError
from pipelex.plugins.anthropic.anthropic_llms import anthropic_list_anthropic_models
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.environment import any_is_placeholder_env, is_env_set

REQUIRED_ENV_VARS = ["ANTHROPIC_API_KEY"]


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
        plugin_for_anthropic: Plugin,
    ):
        if not is_env_set(REQUIRED_ENV_VARS):
            pytest.skip(f"Some key(s) missing amongst {REQUIRED_ENV_VARS}")
        if any_is_placeholder_env(REQUIRED_ENV_VARS):
            pytest.skip(f"Some key(s) among {REQUIRED_ENV_VARS} are a placeholder, can't be used to test listing models")
        try:
            backend = get_models_manager().get_required_inference_backend("anthropic")
            anthropic_models_list = await anthropic_list_anthropic_models(
                plugin=plugin_for_anthropic,
                backend=backend,
            )
        except AuthenticationError as auth_exc:
            pytest.fail(f"Authentication error for Anthropic: {auth_exc}")
        except AnthropicSDKUnsupportedError as exc:
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
