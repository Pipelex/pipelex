import os
from enum import StrEnum

import pytest
from pytest import Config, FixtureRequest, Parser

from pipelex.system.environment import is_env_var_set, is_env_var_truthy, set_env
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.runtime import CODEX_CLOUD_ENV_VAR_KEY, RunMode, runtime_manager
from pipelex.tools.misc.placeholder import make_placeholder_value, value_is_placeholder
from pipelex.tools.misc.pretty import plain_markup_text
from pipelex.tools.misc.rich_extra import is_rich_installed
from pipelex.tools.misc.terminal_utils import print_to_stderr


class ClassRegistryMode(StrEnum):
    SHARED = "shared"
    ISOLATED = "isolated"
    BOTH = "both"


# List of environment variables that may need placeholders in CI
ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI = [
    "PIPELEX_API_KEY",
    "PIPELEX_API_BASE_URL",
    "PIPELEX_INFERENCE_API_KEY",
    "PIPELEX_GATEWAY_API_KEY",
    "OPENAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "AZURE_API_BASE",
    "AZURE_API_KEY",
    "AZURE_API_VERSION",
    "GCP_PROJECT_ID",
    "GCP_LOCATION",
    "GCP_CREDENTIALS_FILE_PATH",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "PERPLEXITY_API_KEY",
    "PERPLEXITY_API_ENDPOINT",
    "PORTKEY_API_KEY",
    "SCALEWAY_ENDPOINT",
    "SCALEWAY_API_KEY",
    "XAI_API_KEY",
    "XAI_API_ENDPOINT",
    "FAL_API_KEY",
    "BLACKBOX_API_KEY",
    "GOOGLE_API_KEY",
    "HF_TOKEN",
    "LINKUP_API_KEY",
    "OPENROUTER_API_KEY",
    "MINIMAX_API_KEY",
]


def _set_test_run_mode() -> None:
    if is_env_var_set(key="GITHUB_ACTIONS") or is_env_var_set(key="CI"):
        runtime_manager.set_run_mode(run_mode=RunMode.CI_TEST)
    elif is_env_var_truthy(key=CODEX_CLOUD_ENV_VAR_KEY):
        # we're in codex cloud and pytest is running, so we are testing in codex cloud
        runtime_manager.set_run_mode(run_mode=RunMode.CODEX_CLOUD_TEST)
    else:
        runtime_manager.set_run_mode(run_mode=RunMode.UNIT_TEST)


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--pipe-run-mode",
        action="store",
        default="dry",
        help="Pipe run mode: 'live' or 'dry'",
        choices=("live", "dry"),
    )
    parser.addoption(
        "--disable-inference",
        action="store_true",
        default=False,
        help="Disable inference for this test session. Uses mock content generator, "
        "skips gateway terms check, and auto-skips tests marked with @pytest.mark.inference.",
    )
    parser.addoption(
        "--class-registry",
        default=ClassRegistryMode.BOTH,
        choices=list(ClassRegistryMode),
        help="Class registry mode: 'both' runs tests in shared and isolated modes (default), "
        "'shared' leaks dynamic classes to global, 'isolated' scopes them to the library registry",
    )


#: What a session stopped for the terms agreement says. Written as Rich markup once: the Rich panel renders it,
#: and the Rich-free path prints the text it renders to, so the message arrives either way.
_TERMS_REQUIRED_MARKUP = (
    "[bold yellow]Pipelex Service Terms Agreement Required[/bold yellow]\n\n"
    "Tests cannot run because Pipelex Gateway is enabled but terms haven't been accepted.\n\n"
    "[bold]To fix this, choose one option:[/bold]\n\n"
    "  [cyan]1.[/cyan] Run [green]pipelex init agreement[/green] to accept terms (quick, no config reset)\n\n"
    "  [cyan]2.[/cyan] Run [green]pipelex init config[/green] to fully reset and configure backends\n\n"
    "  [cyan]3.[/cyan] Disable gateway in [blue].pipelex/inference/backends.toml[/blue]:\n"
    "     [dim]Set pipelex_gateway.enabled = false[/dim]\n"
)

_TERMS_REQUIRED_TITLE = "⚠️  Setup Required"


def _print_terms_required() -> None:
    """Say why the session is stopping, framed by Rich where the extra is installed and plainly where it is not.

    Rich is the ``cli`` extra and this plugin loads in every session of every project that registers it, so the
    message a stopped session depends on is never allowed to depend on it.
    """
    if not is_rich_installed():
        print_to_stderr("")
        print_to_stderr(_TERMS_REQUIRED_TITLE)
        print_to_stderr(plain_markup_text(markup=_TERMS_REQUIRED_MARKUP) or _TERMS_REQUIRED_MARKUP)
        return
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print()
    console.print(Panel(_TERMS_REQUIRED_MARKUP, title=_TERMS_REQUIRED_TITLE, border_style="yellow"))


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Config) -> None:
    """Set the test run mode, then check prerequisites before test collection starts.

    The run mode is set here, first among the configure hooks, rather than in a fixture, because
    it is what keeps the Pipelex Gateway telemetry stream off in a test run: a boot at test-module
    import, during collection or in a later pytest hook happens before any fixture runs, and would
    otherwise see the normal run mode and send the stream.

    Then validates that Pipelex Gateway terms are accepted when gateway is enabled.
    This runs early to provide clear feedback before wasting time on test collection.
    """
    _set_test_run_mode()

    # Skip check when inference is disabled via CLI option
    if config.getoption("--disable-inference", default=False):
        return

    # Skip check in CI environments (IntegrationMode.CI doesn't require terms)
    if is_env_var_set(key="GITHUB_ACTIONS") or is_env_var_set(key="CI"):
        return

    # Skip check in Codex Cloud (terms acceptance handled differently)
    if is_env_var_truthy(key=CODEX_CLOUD_ENV_VAR_KEY):
        return

    # Import here to avoid circular imports during pytest startup
    from pipelex.system.configuration.config_loader import config_manager  # ruff: ignore[import-outside-top-level]
    from pipelex.system.pipelex_service.pipelex_service_config import (  # ruff: ignore[import-outside-top-level]
        is_pipelex_gateway_enabled,
        load_pipelex_service_config_if_exists,
    )

    if not is_pipelex_gateway_enabled():
        return

    pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)

    if pipelex_service_config is None or not pipelex_service_config.agreement.terms_accepted:
        _print_terms_required()
        pytest.exit("Service terms not accepted - run 'pipelex init agreement' first", returncode=1)


@pytest.fixture(scope="session")
def pipe_run_mode(request: FixtureRequest) -> PipeRunMode:
    # Force dry mode when inference is disabled
    if request.config.getoption("--disable-inference", default=False):
        return PipeRunMode.DRY
    mode_str = request.config.getoption("--pipe-run-mode")
    return PipeRunMode(mode_str)


def _setup_env_var_placeholders(env_var_keys: list[str]) -> None:
    """Set placeholder environment variables when running in CI to prevent import failures.

    These placeholders allow the code to import successfully, while actual inference tests
    remain skipped via pytest markers.

    Args:
        env_var_keys: List of environment variable keys that need placeholders

    """
    # Set placeholders for env vars who's presence is required for the code to run properly
    # even if their value is not used in the test
    substitutions_counter = 0
    for key in env_var_keys:
        if not is_env_var_set(key=key):
            placeholder_value = make_placeholder_value(key)
            set_env(key, placeholder_value)
            substitutions_counter += 1

    if substitutions_counter > 0:
        # A plain line rather than a console one: this plugin loads in every session of every project that
        # registers it, and a CI diagnostic must never be the reason a suite cannot run.
        print_to_stderr(f"Set {substitutions_counter} placeholder environment variables")


def _cleanup_placeholder_env_vars(env_var_keys: list[str]) -> None:
    """Remove placeholder environment variables that were set during CI testing.

    This function identifies and removes any environment variables that contain
    placeholder values, cleaning up the environment after tests complete.

    Args:
        env_var_keys: List of environment variable keys to check for placeholders

    """
    removed_counter = 0

    # Check each specified environment variable for placeholder values
    for key in env_var_keys:
        value = os.environ.get(key)
        if value is not None and value_is_placeholder(value):
            del os.environ[key]
            removed_counter += 1

    if removed_counter > 0:
        # As above: a plain line, for the same reason.
        print_to_stderr(f"Cleaned up {removed_counter} placeholder environment variables")


@pytest.fixture(scope="session", autouse=True)
def setup_ci_environment():
    """Set up CI environment variables and configuration before any tests run."""
    env_var_keys = ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI
    if runtime_manager.is_ci_testing:
        _setup_env_var_placeholders(env_var_keys=env_var_keys)
    yield
    # Cleanup placeholder environment variables after tests complete
    if runtime_manager.is_ci_testing:
        _cleanup_placeholder_env_vars(env_var_keys=env_var_keys)


def pytest_collection_modifyitems(  # kw-only: ignore — pytest hookimpl, invoked by pluggy as a framework entrypoint
    config: Config, items: list[pytest.Item]
) -> None:
    """Auto-skip non-dry-runnable inference tests when --disable-inference is set.

    This hook runs after test collection and adds skip markers to tests that:
    - Are marked with @pytest.mark.inference
    - Are NOT marked with @pytest.mark.dry_runnable

    Tests marked with both inference and dry_runnable can still run because
    the cogt leaf mocks under run_mode=DRY.
    """
    if not config.getoption("--disable-inference", default=False):
        return

    skip_inference = pytest.mark.skip(reason="Inference disabled via --disable-inference (test is not dry_runnable)")
    for item in items:
        if "inference" in item.keywords and "dry_runnable" not in item.keywords:
            item.add_marker(skip_inference)


def needs_inference_in_pipelex(request: FixtureRequest) -> bool:
    """Check if inference is needed for this test session.

    Use this helper in your conftest.py to pass the needs_inference flag
    to Pipelex.make():

        from pipelex.test_extras.shared_pytest_plugins import needs_inference_in_pipelex

        @pytest.fixture(scope="module", autouse=True)
        def reset_pipelex_config_fixture(request):
            pipelex_instance = Pipelex.make(
                needs_inference=needs_inference_in_pipelex(request),
            )

            yield
            pipelex_instance.teardown()

    Args:
        request: The pytest FixtureRequest object.

    Returns:
        True if inference is needed, False if --disable-inference was passed.
    """
    return not bool(request.config.getoption("--disable-inference", default=False))


def is_inference_disabled_in_pipelex(request: FixtureRequest) -> bool:
    """Deprecated: use needs_inference_in_pipelex() instead.

    Kept for backward compatibility with external repos.
    """
    return not needs_inference_in_pipelex(request)
