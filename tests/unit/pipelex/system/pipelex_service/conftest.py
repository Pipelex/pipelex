"""Conftest for pipelex_service unit tests.

These tests are pure unit tests that don't need Pipelex initialization.
We override the autouse fixture from the root conftest to disable it.
"""

import pytest
from pytest_mock import MockerFixture


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture():
    """Override the root conftest fixture to disable Pipelex initialization for these tests.

    We mock the log module to avoid needing full Pipelex setup.
    """
    return


@pytest.fixture(autouse=True)
def mock_log(mocker: MockerFixture):
    """Mock the log module for all tests in this package."""
    mock_logger = mocker.MagicMock()
    mocker.patch("pipelex.system.pipelex_service.gateway_config_merger.log", mock_logger)
    mocker.patch("pipelex.system.pipelex_service.remote_config_cache.log", mock_logger)
    return mock_logger
