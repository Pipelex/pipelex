from collections.abc import Iterator

import pytest

from pipelex.plugins.document_renderer_registry import DocumentRendererRegistry
from pipelex.runtime_hub import get_document_renderer_registry, get_runtime_hub
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines


@pytest.fixture
def stub_engines() -> Iterator[StubEngines]:
    """Replace the runtime's document engines with stubs for one test, and put the booted ones back after."""
    booted_registry = get_document_renderer_registry()
    engines = StubEngines()
    get_runtime_hub().set_document_renderer_registry(engines.registry())
    try:
        yield engines
    finally:
        get_runtime_hub().set_document_renderer_registry(booted_registry)


@pytest.fixture
def no_engines() -> Iterator[None]:
    """A runtime with no document engine, as a host that disables the built-in one and installs no plugin."""
    booted_registry = get_document_renderer_registry()
    get_runtime_hub().set_document_renderer_registry(DocumentRendererRegistry(entries={}, engine_choices={}))
    try:
        yield
    finally:
        get_runtime_hub().set_document_renderer_registry(booted_registry)
