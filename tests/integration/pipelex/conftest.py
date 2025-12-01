"""Integration test configuration and fixtures.

This conftest.py coordinates pytest hooks and imports fixtures from organized modules.
"""

from typing import Any

import pytest

# Import all fixtures from fixture modules
from .fixtures.extract_fixtures import (
    extract_choice_for_image,
    extract_choice_for_pdf,
    extract_handle,
    extract_handle_from_image,
)
from .fixtures.img_gen_fixtures import img_gen_handle
from .fixtures.llm_fixtures import llm_handle, llm_job_params, llm_preset_id
from .fixtures.plugin_fixtures import openai_endpoint, plugin_for_anthropic, plugin_for_openai
from .fixtures.routing_fixtures import (
    check_backend_supports_model,
    extract_backend_from_profile_name_if_possible,
    get_all_routing_profiles,
    routing_profile_override,
    routing_profile_setup,
)

# Make fixtures available (prevent unused import warnings)
__all__ = [
    # Routing fixtures
    "routing_profile_setup",
    "routing_profile_override",
    # LLM fixtures
    "llm_preset_id",
    "llm_handle",
    "llm_job_params",
    # Plugin fixtures
    "plugin_for_openai",
    "plugin_for_anthropic",
    "openai_endpoint",
    # Image generation fixtures
    "img_gen_handle",
    # Extract fixtures
    "extract_handle",
    "extract_handle_from_image",
    "extract_choice_for_pdf",
    "extract_choice_for_image",
]


def pytest_collection_modifyitems(items: list[pytest.Item], config: pytest.Config):  # noqa: ARG001
    """Skip test items where routing profile doesn't support the LLM handle (at collection time)."""
    skipped_count = 0
    for item in items:
        # Only process items that have both routing_profile_setup and llm_handle
        if not hasattr(item, "callspec"):
            continue

        callspec = item.callspec  # type: ignore[attr-defined]
        callspec_params: dict = callspec.params  # type: ignore[attr-defined]

        # Check for the routing_profile_setup parameter (set by our fixture)
        if "routing_profile_setup" not in callspec_params or "llm_handle" not in callspec_params:
            continue

        routing_profile = callspec_params.get("routing_profile_setup")  # type: ignore[attr-defined]
        llm_handle = callspec_params.get("llm_handle")  # type: ignore[attr-defined]

        # Type check to ensure we have strings
        if not isinstance(routing_profile, str) or not isinstance(llm_handle, str):
            continue

        # Extract backend name from routing profile
        backend_name = extract_backend_from_profile_name_if_possible(routing_profile)
        if not backend_name:
            continue

        # Check if this backend supports this model
        if not check_backend_supports_model(backend_name, llm_handle):
            # Add skip marker
            item.add_marker(pytest.mark.skip(reason=f"Backend '{backend_name}' does not support LLM handle '{llm_handle}'"))
            skipped_count += 1


def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:  # noqa: ARG001
    """Count backend incompatibility skips for summary message.

    Since we use -rfE in pyproject.toml, skips are already hidden from output.
    This hook just counts them for our custom summary message.
    """
    if not hasattr(session.config, "pluginmanager"):
        return

    terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is None or not hasattr(terminal_reporter, "stats"):
        return

    # Count backend incompatibility skips
    if "skipped" in terminal_reporter.stats:
        hidden_count = 0
        for skip_report in terminal_reporter.stats["skipped"]:
            reason = ""
            if hasattr(skip_report, "longrepr"):
                if isinstance(skip_report.longrepr, tuple) and len(skip_report.longrepr) >= 3:  # type: ignore[arg-type]
                    reason = str(skip_report.longrepr[2])  # type: ignore[index]
                else:
                    reason = str(skip_report.longrepr)  # type: ignore[arg-type]

            if "does not support LLM handle" in reason:
                hidden_count += 1

        if hidden_count > 0:
            terminal_reporter._pipelex_hidden_skip_count = hidden_count  # type: ignore[attr-defined] # noqa: SLF001


def pytest_terminal_summary(terminalreporter: Any, exitstatus: Any, config: pytest.Config) -> None:  # noqa: ARG001
    """Print summary of hidden backend incompatibility skips.

    This runs after the standard summary and adds our custom message.
    """
    # Check if we counted any hidden skips
    if hasattr(terminalreporter, "_pipelex_hidden_skip_count"):
        hidden_count = terminalreporter._pipelex_hidden_skip_count  # type: ignore[attr-defined] # noqa: SLF001

        if hidden_count > 0:
            # Add spacing for readability
            terminalreporter.write_line("")

            message = f"({hidden_count} backend incompatibility {'skip' if hidden_count == 1 else 'skips'} hidden)"
            terminalreporter.write_line(message, cyan=True)


def pytest_generate_tests(metafunc: pytest.Metafunc):
    """Dynamically parametrize routing_profile_setup only for modules that need it."""
    # Only parametrize if the test uses routing_profile_override
    if "routing_profile_override" in metafunc.fixturenames:
        # Parametrize routing_profile_setup (which will be consumed by reset_pipelex_config_fixture)
        if "routing_profile_setup" in metafunc.fixturenames:
            metafunc.parametrize("routing_profile_setup", get_all_routing_profiles(), indirect=True, scope="module")
