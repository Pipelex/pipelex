"""Fixtures shared by the hosted provider's unit tests."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorVocabulary
from pipelex.providers.pipelex_hosted.pipelex_hosted_error_codes import PIPELEX_HOSTED_SERVICE_ERROR_CODES


@pytest.fixture(autouse=True)
def pipelex_hosted_service_error_vocabulary(mocker: MockerFixture) -> ServiceErrorVocabulary:
    """Hand the classifier the vocabulary the hosted plugin contributes, as a booted runtime has it.

    The Pipelex service's own refusal codes are classified only because the plugin contributes them
    through the service error vocabulary, so every test here classifies against exactly that
    vocabulary, stated rather than inherited from whatever the session's boot registered. A test that
    needs the status ladder alone patches the same accessor to return ``None``.
    """
    vocabulary = ServiceErrorVocabulary({entry.code: entry for entry in PIPELEX_HOSTED_SERVICE_ERROR_CODES})
    mocker.patch("pipelex.cogt.inference.error_classify.get_optional_service_error_vocabulary", return_value=vocabulary)
    return vocabulary
