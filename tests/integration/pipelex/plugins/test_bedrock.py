import warnings
from typing import Any, Dict, List

import boto3
import pytest
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex.tools.environment import any_is_placeholder_env, is_env_set

warnings.filterwarnings(
    "ignore",
    message=r".*datetime\.datetime\.utcnow\(\).*",
    category=DeprecationWarning,
)
# Apply pytest-level filter to ensure the warning is suppressed during test collection and execution
pytestmark = pytest.mark.filterwarnings("ignore:.*datetime\\.datetime\\.utcnow\\(\\).*:DeprecationWarning")

REQUIRED_ENV_VARS = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]


# make t VERBOSE=2 TEST=TestBedrock
@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
class TestBedrock:
    # pytest -k test_bedrock_list_available_models -s -vv
    def test_bedrock_list_available_models(
        self,
        pytestconfig: pytest.Config,
        bedrock_provider: str,
        bedrock_region_name: str,
    ):
        if not is_env_set(REQUIRED_ENV_VARS):
            pytest.skip(f"Some key(s) missing amongst {REQUIRED_ENV_VARS}")
        if any_is_placeholder_env(REQUIRED_ENV_VARS):
            pytest.skip(f"Some key(s) among {REQUIRED_ENV_VARS} are a placeholder, can't be used to test listing models")
        client = boto3.client("bedrock", region_name=bedrock_region_name)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        response: Dict[str, Any] = client.list_foundation_models(byProvider=bedrock_provider)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        bedrock_models_list: List[Dict[str, Any]] = response["modelSummaries"]  # pyright: ignore[reportUnknownVariableType]
        if pytestconfig.get_verbosity() >= 2:
            # Create and configure the table
            console = Console()
            table = Table(
                title=f"Models from {bedrock_provider} available for Bedrock in {bedrock_region_name}",
                show_header=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
            )

            # Add columns
            table.add_column("Model ID", style="green")
            table.add_column("Model ARN", style="yellow")

            # Add rows
            for model in bedrock_models_list:  # pyright: ignore[reportUnknownVariableType]
                table.add_row(model["modelId"], model["modelArn"])  # pyright: ignore[reportUnknownArgumentType]

            # Print the table
            console.print("\n")
            console.print(table)
            console.print("\n")

    # pytest -k test_bedrock_list_inference_profiles -s -vv
    def test_bedrock_list_inference_profiles(
        self,
        pytestconfig: pytest.Config,
        bedrock_region_name: str,
    ):
        if not is_env_set(REQUIRED_ENV_VARS):
            pytest.skip(f"Some key(s) missing amongst {REQUIRED_ENV_VARS}")
        if any_is_placeholder_env(REQUIRED_ENV_VARS):
            pytest.skip(f"Some key(s) among {REQUIRED_ENV_VARS} are a placeholder, can't be used to test listing models")
        client = boto3.client("bedrock", region_name=bedrock_region_name)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        response: Dict[str, Any] = client.list_inference_profiles()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        inference_profiles_list: List[Dict[str, Any]] = response["inferenceProfileSummaries"]  # pyright: ignore[reportUnknownVariableType]
        if pytestconfig.get_verbosity() >= 2:
            # Create and configure the table
            console = Console()
            table = Table(
                title=f"Inference Profiles Available for Bedrock in {bedrock_region_name}",
                show_header=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
            )

            # Add columns
            table.add_column("Profile ID", style="green")
            table.add_column("Profile ARN", style="yellow")

            # Add rows
            for profile in inference_profiles_list:  # pyright: ignore[reportUnknownVariableType]
                table.add_row(profile["inferenceProfileId"], profile["inferenceProfileArn"])  # pyright: ignore[reportUnknownArgumentType]

            # Print the table
            console.print("\n")
            console.print(table)
            console.print("\n")
