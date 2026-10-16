"""Shared fixtures for the error registry tests: the committed registry, the standard's schema and the core registry."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.dev_cli.commands.error_registry.registry_outputs import load_core_registry
from pipelex.cli.dev_cli.commands.error_registry.registry_source import STANDARD_SCHEMA_PATH, load_composed_document, load_json_file

if TYPE_CHECKING:
    from pipelex.errors.registry.registry_document import ErrorRegistryDocument


@pytest.fixture
def composed_document() -> dict[str, Any]:
    """A fresh copy of the registry document composed from the committed source, safe to mutate."""
    return copy.deepcopy(load_composed_document())


@pytest.fixture
def standard_schema() -> dict[str, Any]:
    """The registry format's JSON Schema, vendored from the standard."""
    schema: dict[str, Any] = load_json_file(path=STANDARD_SCHEMA_PATH)
    return schema


@pytest.fixture
def core_registry() -> ErrorRegistryDocument:
    """The MTHDS core registry, from the vendored snapshot."""
    return load_core_registry()
