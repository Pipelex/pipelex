import pytest
from pytest import FixtureRequest, Parser
from rich import print

from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.tools.environment import ENV_DUMMY_PLACEHOLDER_VALUE, is_env_set, set_env
from pipelex.tools.runtime_manager import RunMode, runtime_manager


@pytest.fixture(scope="session", autouse=True)
def set_run_mode():
    if is_env_set("GITHUB_ACTIONS") or is_env_set("CI"):
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


def _setup_env_var_placeholders():
    """Set placeholder environment variables when running in CI to prevent import failures.

    These placeholders allow the code to import successfully, while actual inference tests
    remain skipped via pytest markers.
    """

    # Define placeholder values for all inference-related env vars
    env_var_placeholders = {
        "PIPELEX_API_TOKEN": ENV_DUMMY_PLACEHOLDER_VALUE,
        "PIPELEX_API_BASE_URL": ENV_DUMMY_PLACEHOLDER_VALUE,
        "PIPELEX_INFERENCE_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "OPENAI_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "AWS_ACCESS_KEY_ID": ENV_DUMMY_PLACEHOLDER_VALUE,
        "AWS_SECRET_ACCESS_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "AWS_REGION": ENV_DUMMY_PLACEHOLDER_VALUE,
        "AZURE_API_BASE": ENV_DUMMY_PLACEHOLDER_VALUE,
        "AZURE_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "AZURE_API_VERSION": ENV_DUMMY_PLACEHOLDER_VALUE,
        "GCP_PROJECT_ID": ENV_DUMMY_PLACEHOLDER_VALUE,
        "GCP_LOCATION": ENV_DUMMY_PLACEHOLDER_VALUE,
        "GCP_CREDENTIALS_FILE_PATH": ENV_DUMMY_PLACEHOLDER_VALUE,
        "ANTHROPIC_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "MISTRAL_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "PERPLEXITY_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "PERPLEXITY_API_ENDPOINT": ENV_DUMMY_PLACEHOLDER_VALUE,
        "XAI_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "XAI_API_ENDPOINT": ENV_DUMMY_PLACEHOLDER_VALUE,
        "FAL_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
        "BLACKBOX_API_KEY": ENV_DUMMY_PLACEHOLDER_VALUE,
    }

    # Set placeholders for env vars who's presence is required for the code to run properly
    # even if their value is not used in the test
    substitutions_counter = 0
    for key, placeholder_value in env_var_placeholders.items():
        if not is_env_set(key):
            set_env(key, placeholder_value)
            substitutions_counter += 1

    if substitutions_counter > 0:
        print(f"[yellow]Set {substitutions_counter} placeholder environment variables[/yellow]")


@pytest.fixture(scope="session", autouse=True)
def setup_ci_environment():
    """Set up CI environment variables and configuration before any tests run."""
    # Check if we're running in CI (GitHub Actions or generic CI environment)
    if runtime_manager.is_unit_testing:
        _setup_env_var_placeholders()
    yield
