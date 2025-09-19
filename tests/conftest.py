import pytest
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
