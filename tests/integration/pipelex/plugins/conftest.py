import pytest

from pipelex.cogt.exceptions import ModelManagerError
from pipelex.hub import get_models_manager


def is_backend_available(backend_name: str) -> bool:
    """Check if an inference backend is available/enabled."""
    try:
        get_models_manager().get_required_inference_backend(backend_name)
        return True
    except ModelManagerError:
        return False


@pytest.fixture(params=["anthropic", "mistral", "meta", "amazon"])
def bedrock_provider(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(params=["us-east-1", "us-west-2"])
def bedrock_region_name(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
