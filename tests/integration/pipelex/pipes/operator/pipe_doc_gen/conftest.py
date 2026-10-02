import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from pipelex.cogt.doc_gen.exceptions import BUILT_IN_DOC_GEN_MODEL
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.runtime_hub import get_inference_backend_registry, get_models_manager, get_runtime_hub
from pipelex.system.configuration.config_loader import config_manager
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, make_doc_gen_backends, make_models_manager


@pytest.fixture
def stub_engines() -> Iterator[StubEngines]:
    """Install a stub document generation plugin for one test, and put the booted engines and model deck back after.

    The stub registers as the real plugin does: a worker per sdk, which replaces the runtime's document engines, and
    the plugin's models and deck defaults, which a model manager set up with its declarations merges.
    """
    booted_registry = get_inference_backend_registry()
    booted_models_manager = get_models_manager()
    engines = StubEngines()
    registrar = engines.make_registrar()
    get_runtime_hub().set_inference_backend_registry(
        booted_registry.with_family(family=InferenceFamily.DOC_GEN, backends=make_doc_gen_backends(registrar=registrar))
    )
    get_runtime_hub().set_models_manager(models_manager=make_models_manager(plugin_model_declarations=registrar.make_model_declarations()))
    try:
        yield engines
    finally:
        get_runtime_hub().set_inference_backend_registry(booted_registry)
        get_runtime_hub().set_models_manager(models_manager=booted_models_manager)


@pytest.fixture
def no_engines() -> Iterator[None]:
    """A runtime with no document engine, as a host that disables the built-in one and installs no plugin."""
    booted_registry = get_inference_backend_registry()
    get_runtime_hub().set_inference_backend_registry(booted_registry.with_family(family=InferenceFamily.DOC_GEN, backends={}))
    try:
        yield
    finally:
        get_runtime_hub().set_inference_backend_registry(booted_registry)


@pytest.fixture
def stale_internal_backend(tmp_path: Path) -> Iterator[None]:
    """An installation whose `internal.toml` predates the built-in engine: this runtime's backends, without `reportlab-pdf`."""
    backends_dir = tmp_path / "backends"
    shutil.copytree(config_manager.backends_dir_path, backends_dir)
    internal_toml_path = backends_dir / "internal.toml"
    internal_toml = load_toml_with_tomlkit(internal_toml_path)
    del internal_toml[BUILT_IN_DOC_GEN_MODEL]
    save_toml_to_path(internal_toml, path=internal_toml_path)
    booted_models_manager = get_models_manager()
    get_runtime_hub().set_models_manager(
        models_manager=make_models_manager(plugin_model_declarations=PluginModelDeclarations.make_empty(), backends_dir_path=backends_dir)
    )
    try:
        yield
    finally:
        get_runtime_hub().set_models_manager(models_manager=booted_models_manager)
