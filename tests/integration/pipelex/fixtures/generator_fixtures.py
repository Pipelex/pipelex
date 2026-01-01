from pathlib import Path

import pytest

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider


@pytest.fixture
def generated_content_factory(tmp_path: Path) -> GeneratedContentFactory:
    """Create a GeneratedContentFactory with a local storage provider."""
    storage_provider = LocalStorageProvider(root_path=tmp_path)
    return GeneratedContentFactory(storage_provider=storage_provider)


@pytest.fixture
def content_generator(generated_content_factory: GeneratedContentFactory) -> ContentGeneratorProtocol:
    """Provide a ContentGeneratorProtocol instance for testing."""
    return ContentGenerator(generated_content_factory=generated_content_factory)
