import pytest
from pytest import FixtureRequest, Parser
from rich import print

from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.tools.environment import is_env_set, set_env
from pipelex.tools.misc.placeholder import make_placeholder_value
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

    # Define list of inference-related env vars that need placeholders
    env_var_names = [
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
    ]

    # Set placeholders for env vars who's presence is required for the code to run properly
    # even if their value is not used in the test
    substitutions_counter = 0
    for key in env_var_names:
        if not is_env_set([key]):
            placeholder_value = make_placeholder_value(key)
            set_env(key, placeholder_value)
            substitutions_counter += 1

    if substitutions_counter > 0:
        print(f"[yellow]Set {substitutions_counter} placeholder environment variables[/yellow]")


@pytest.fixture(scope="session", autouse=True)
def setup_ci_environment():
    """Set up CI environment variables and configuration before any tests run."""
    if runtime_manager.is_ci_testing:
        _setup_env_var_placeholders()
    yield
