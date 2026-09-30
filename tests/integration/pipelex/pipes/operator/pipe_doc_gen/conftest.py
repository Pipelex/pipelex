from collections.abc import Iterator

import pytest

from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.runtime_hub import get_inference_backend_registry, get_runtime_hub
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines


@pytest.fixture
def stub_engines() -> Iterator[StubEngines]:
    """Stand stub workers in for the runtime's document engines for one test, and put the booted ones back after."""
    booted_registry = get_inference_backend_registry()
    engines = StubEngines()
    get_runtime_hub().set_inference_backend_registry(booted_registry.with_family(family=InferenceFamily.DOC_GEN, backends=engines.backends()))
    try:
        yield engines
    finally:
        get_runtime_hub().set_inference_backend_registry(booted_registry)


@pytest.fixture
def no_engines() -> Iterator[None]:
    """A runtime with no document engine, as a host that disables the built-in one and installs no plugin."""
    booted_registry = get_inference_backend_registry()
    get_runtime_hub().set_inference_backend_registry(booted_registry.with_family(family=InferenceFamily.DOC_GEN, backends={}))
    try:
        yield
    finally:
        get_runtime_hub().set_inference_backend_registry(booted_registry)
