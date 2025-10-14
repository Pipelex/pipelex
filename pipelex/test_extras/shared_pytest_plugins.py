import os

import pytest
from pytest import FixtureRequest, Parser
from rich import print  # noqa: A004

from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.system.environment import is_env_var_set, set_env
from pipelex.system.runtime import RunMode, runtime_manager
from pipelex.tools.misc.placeholder import make_placeholder_value, value_is_placeholder

# List of environment variables that may need placeholders in CI
ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI = [
    "PIPELEX_API_TOKEN",
    "PIPELEX_API_BASE_URL",
    "PIPELEX_INFERENCE_API_KEY",
    "OPENAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "AZURE_API_BASE",
    "AZURE_API_KEY",
    "AZURE_API_VERSION",
    "GCP_PROJECT_ID",
    "GCP_LOCATION",
    "GCP_CREDENTIALS_FILE_PATH",
    "ANTHROPIC_API_KEY",
    "MISTRAL_API_KEY",
    "PERPLEXITY_API_KEY",
    "PERPLEXITY_API_ENDPOINT",
    "XAI_API_KEY",
    "XAI_API_ENDPOINT",
    "FAL_API_KEY",
    "BLACKBOX_API_KEY",
    "GOOGLE_API_KEY",
]


@pytest.fixture(scope="session", autouse=True)
def set_run_mode():
    if is_env_var_set(key="GITHUB_ACTIONS") or is_env_var_set(key="CI"):
        runtime_manager.set_run_mode(run_mode=RunMode.CI_TEST)
    else:
        runtime_manager.set_run_mode(run_mode=RunMode.UNIT_TEST)


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--pipe-run-mode",
        action="store",
        default="dry",
        help="Pipe run mode: 'live' or 'dry'",
        choices=("live", "dry"),
    )


@pytest.fixture
def pipe_run_mode(request: FixtureRequest) -> PipeRunMode:
    mode_str = request.config.getoption("--pipe-run-mode")
    return PipeRunMode(mode_str)


def _setup_env_var_placeholders(env_var_keys: list[str]) -> None:
    """Set placeholder environment variables when running in CI to prevent import failures.

    These placeholders allow the code to import successfully, while actual inference tests
    remain skipped via pytest markers.

    Args:
        env_var_keys: List of environment variable keys that need placeholders

    """
    # Set placeholders for env vars who's presence is required for the code to run properly
    # even if their value is not used in the test
    substitutions_counter = 0
    for key in env_var_keys:
        if not is_env_var_set(key=key):
            placeholder_value = make_placeholder_value(key)
            set_env(key, placeholder_value)
            substitutions_counter += 1

    if substitutions_counter > 0:
        print(f"[yellow]Set {substitutions_counter} placeholder environment variables[/yellow]")


def _cleanup_placeholder_env_vars(env_var_keys: list[str]) -> None:
    """Remove placeholder environment variables that were set during CI testing.

    This function identifies and removes any environment variables that contain
    placeholder values, cleaning up the environment after tests complete.

    Args:
        env_var_keys: List of environment variable keys to check for placeholders

    """
    removed_counter = 0

    # Check each specified environment variable for placeholder values
    for key in env_var_keys:
        value = os.environ.get(key)
        if value is not None and value_is_placeholder(value):
            del os.environ[key]
            removed_counter += 1

    if removed_counter > 0:
        print(f"[yellow]Cleaned up {removed_counter} placeholder environment variables[/yellow]")


@pytest.fixture(scope="session", autouse=True)
def setup_ci_environment():
    """Set up CI environment variables and configuration before any tests run."""
    env_var_keys = ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI
    if runtime_manager.is_ci_testing:
        _setup_env_var_placeholders(env_var_keys=env_var_keys)
    yield
    # Cleanup placeholder environment variables after tests complete
    if runtime_manager.is_ci_testing:
        _cleanup_placeholder_env_vars(env_var_keys=env_var_keys)
