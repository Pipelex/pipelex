"""Agent CLI command to accept Pipelex Gateway terms and mark inference setup complete."""

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    update_inference_setup_completed,
    update_service_terms_acceptance,
)


def agent_accept_gateway_terms_cmd() -> None:
    """Accept Pipelex Gateway terms and mark inference setup as completed.

    Records the user's acceptance of the Pipelex Gateway Terms of Service
    and Privacy Policy, and marks inference setup as completed so the
    first-run onboarding flow does not trigger again.
    """
    try:
        config_dir = config_manager.global_config_dir
        config_dir.mkdir(parents=True, exist_ok=True)
        update_service_terms_acceptance(accepted=True, config_dir=config_dir)
        update_inference_setup_completed(completed=True, config_dir=config_dir)
        agent_success(
            {
                "success": True,
                "terms_accepted": True,
                "inference_setup_completed": True,
            }
        )
    except typer.Exit:
        raise
    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(
            f"Failed to accept gateway terms: {exc}",
            error_type=type(exc).__name__,
            cause=exc,
        )
