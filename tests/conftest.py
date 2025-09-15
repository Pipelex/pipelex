import os

import pytest
from rich import print
from rich.console import Console
from rich.traceback import Traceback

import pipelex.config
import pipelex.pipelex
from pipelex import log
from pipelex.config import get_config
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.hub import get_concept_provider
from tests.cases.registry import Fruit

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"


def _setup_ci_env_vars():
    """Set placeholder environment variables when running in CI to prevent import failures.

    These placeholders allow the code to import successfully, while actual inference tests
    remain skipped via pytest markers.
    """
    # Check if we're running in CI (GitHub Actions or generic CI environment)
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        print("[yellow]CI environment detected - setting placeholder API keys[/yellow]")

        # Define placeholder values for all inference-related env vars
        ci_placeholders = {
            "PIPELEX_API_TOKEN": "ci-placeholder-token",
            "PIPELEX_API_BASE_URL": "https://app.pipelex.ai/api/v1",
            "OPENAI_API_KEY": "sk-ci-placeholder-key",
            "AWS_ACCESS_KEY_ID": "ci-placeholder-aws-key",
            "AWS_SECRET_ACCESS_KEY": "ci-placeholder-aws-secret",
            "AWS_REGION": "us-east-1",
            "AZURE_OPENAI_API_ENDPOINT": "https://ci-placeholder.openai.azure.com",
            "AZURE_OPENAI_API_VERSION": "2025-04-01-preview",
            "AZURE_OPENAI_API_KEY": "ci-placeholder-azure-key",
            "ANTHROPIC_API_KEY": "sk-ant-ci-placeholder-key",
            "MISTRAL_API_KEY": "ci-placeholder-mistral-key",
            "PERPLEXITY_API_KEY": "ci-placeholder-perplexity-key",
            "PERPLEXITY_API_ENDPOINT": "https://api.perplexity.ai",
            "FAL_API_KEY": "ci-placeholder-fal-key",
            "GCP_PROJECT_ID": "ci-placeholder-project",
            "GCP_REGION": "us-central1",
            # GCP_CREDENTIALS_FILE_PATH intentionally omitted - let it be None if not set
            "XAI_API_KEY": "ci-placeholder-xai-key",
            "XAI_API_ENDPOINT": "https://api.x.ai/v1/",
            "CUSTOM_ENDPOINT_BASE_URL": "http://localhost:11434/v1/",
            "CUSTOM_ENDPOINT_API_KEY": "ci-placeholder-custom-key",
        }

        # Set placeholders, overriding any existing values in CI
        # This ensures tests won't accidentally use real API keys in CI
        for key, value in ci_placeholders.items():
            os.environ[key] = value

        print(f"[yellow]Set {len(ci_placeholders)} placeholder environment variables[/yellow]")


# Set up CI environment variables before any imports that might need them
_setup_ci_env_vars()


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture():
    # Code to run before each test
    print("[magenta]pipelex setup[/magenta]")
    try:
        pipelex_instance = pipelex.pipelex.Pipelex.make(relative_config_folder_path="../pipelex/libraries")
        config = get_config()
        log.verbose(config, title="Test config")
        assert isinstance(config, pipelex.config.PipelexConfig)
        assert config.project_name == "pipelex"
    except Exception as exc:
        Console().print(Traceback())
        pytest.exit(f"Critical Pipelex setup error: {exc}")
    yield
    # Code to run after each test
    print("[magenta]pipelex teardown[/magenta]")
    pipelex_instance.teardown()


@pytest.fixture(scope="function", autouse=True)
def pretty():
    # Code to run before each test
    yield
    # Code to run after each test


# Test data fixtures
@pytest.fixture(scope="session")
def apple() -> Fruit:
    """Apple fruit fixture."""
    return Fruit(name="apple", color="red")


@pytest.fixture(scope="session")
def cherry() -> Fruit:
    """Cherry fruit fixture."""
    return Fruit(name="cherry", color="red")


@pytest.fixture(scope="session")
def blueberry() -> Fruit:
    """Blueberry fruit fixture."""
    return Fruit(name="blueberry", color="blue")


@pytest.fixture(scope="module")
def concept_provider() -> ConceptProviderAbstract:
    """Concept provider fixture for testing concept compatibility."""
    return get_concept_provider()
