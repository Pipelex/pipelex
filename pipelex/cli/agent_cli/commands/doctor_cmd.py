"""Agent CLI doctor command -- JSON health report with no interactive prompts."""

from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.cli.commands.doctor_cmd import (
    ConfigLocationInfo,
    check_backend_credentials,
    check_config_files,
    check_models,
    check_telemetry_config,
    gather_config_location,
)
from pipelex.system.configuration.config_loader import config_manager


def agent_doctor_cmd(
    global_: Annotated[
        bool,
        typer.Option(
            "--global",
            "-g",
            help="Force checking the global ~/.pipelex/ directory.",
        ),
    ] = False,
) -> None:
    """Check Pipelex configuration health and output a JSON report.

    Unlike the human CLI doctor, this command:
    - Outputs structured JSON to stdout (never Rich panels or colors)
    - Does not offer interactive fixes (diagnostic-only)
    - Includes ``recommended_actions`` for programmatic remediation

    Target directory: auto-detects project .pipelex/ if present, else ~/.pipelex/.
    Use --global/-g to force checking the global ~/.pipelex/ directory.
    """
    try:
        # When --global, force checking ~/.pipelex/ only; otherwise use layered resolution
        config_dir = config_manager.global_config_dir if global_ else None

        # Gather config location info (override for --global flag)
        if global_:
            config_location = ConfigLocationInfo(
                config_dir=str(config_manager.global_config_dir),
                is_project_local=False,
                project_root=None,
                global_config_dir=str(config_manager.global_config_dir),
            )
        else:
            config_location = gather_config_location()

        config_healthy, config_missing_count, config_message = check_config_files(config_dir=config_dir)
        telemetry_healthy, telemetry_message = check_telemetry_config(config_dir=config_dir)
        backends_healthy, backend_credential_reports, backends_message = check_backend_credentials(config_dir=config_dir)
        models_healthy, models_message, backend_file_reports = check_models(config_dir=config_dir)
    except Exception as exc:
        agent_error(f"Health check failed unexpectedly: {exc}", type(exc).__name__, cause=exc)
        # agent_error has NoReturn

    all_healthy = config_healthy and telemetry_healthy and backends_healthy and models_healthy

    # Build backend credential details
    backends_list: list[dict[str, Any]] = []
    for backend_name, report in backend_credential_reports.items():
        backend_entry: dict[str, Any] = {
            "backend_name": backend_name,
            "all_credentials_valid": report.all_credentials_valid,
        }
        if report.missing_vars:
            backend_entry["missing_vars"] = report.missing_vars
        if report.placeholder_vars:
            backend_entry["placeholder_vars"] = report.placeholder_vars
        backends_list.append(backend_entry)

    # Build backend file details
    backend_files_list: list[dict[str, Any]] = []
    for backend_name, file_report in backend_file_reports.items():
        file_entry: dict[str, Any] = {
            "backend_name": backend_name,
            "file_path": file_report.file_path,
            "is_valid": file_report.is_valid,
        }
        if file_report.error_message:
            file_entry["error_message"] = file_report.error_message
        if file_report.has_kit_template:
            file_entry["has_kit_template"] = True
        backend_files_list.append(file_entry)

    # Build recommended actions
    recommended_actions: list[str] = []
    if not config_healthy and config_missing_count > 0:
        recommended_actions.append("Run 'pipelex init config' to install missing configuration files")
    if not config_healthy and config_missing_count == 0:
        recommended_actions.append(f"Fix validation errors in {config_location.config_dir}/pipelex.toml or run 'pipelex init config'")
    if not telemetry_healthy:
        recommended_actions.append(f"Run 'pipelex init telemetry' to fix telemetry: {telemetry_message}")
    if not backends_healthy:
        for report in backend_credential_reports.values():
            if report.missing_vars:
                for var_name in report.missing_vars:
                    recommended_actions.append(f"Set environment variable: {var_name}")
            if report.placeholder_vars:
                for var_name in report.placeholder_vars:
                    recommended_actions.append(f"Replace placeholder value for environment variable: {var_name}")
    if not models_healthy:
        for file_report in backend_file_reports.values():
            if not file_report.is_valid and file_report.has_kit_template:
                recommended_actions.append(f"Run 'pipelex doctor --fix' to replace outdated backend config: {file_report.backend_name}")
            elif not file_report.is_valid:
                recommended_actions.append(
                    f"Manually fix backend configuration in {config_location.config_dir}/inference/backends/{file_report.backend_name}.toml"
                )

    result: dict[str, Any] = {
        "success": True,
        "all_healthy": all_healthy,
        "config_location": config_location.model_dump(),
        "checks": {
            "config_files": {
                "healthy": config_healthy,
                "message": config_message,
                "missing_count": config_missing_count,
            },
            "telemetry": {
                "healthy": telemetry_healthy,
                "message": telemetry_message,
            },
            "backend_credentials": {
                "healthy": backends_healthy,
                "message": backends_message,
                "backends": backends_list,
            },
            "models": {
                "healthy": models_healthy,
                "message": models_message,
                "backend_files": backend_files_list,
            },
        },
    }

    if recommended_actions:
        result["recommended_actions"] = recommended_actions

    agent_success(result)
