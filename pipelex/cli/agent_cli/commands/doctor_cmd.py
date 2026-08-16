"""Agent CLI doctor command -- health report with no interactive prompts."""

from typing import Annotated, Any

import typer

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.agent_cli.commands.agent_cli_factory import (
    AGENT_CLI_STDERR_LOG_FIELDS,
    apply_agent_cli_output_discipline,
    silence_logging_for_agent_cli,
)
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success, set_agent_cli_error_format
from pipelex.cli.commands.doctor_cmd import (
    BackendFileReport,
    ConfigLocationInfo,
    PendingMigrationsCheck,
    PendingMigrationsFinding,
    TelemetryConfigCheck,
    TelemetryConfigFinding,
    check_backend_credentials,
    check_config_files,
    check_models,
    check_pending_migrations,
    check_telemetry_config,
    gather_config_location,
    setup_doctor_runtime,
)
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.system.configuration.config_loader import config_manager


def _status_icon(*, healthy: bool) -> str:
    """Return a status emoji: checkmark for healthy, warning for unhealthy."""
    return "\u2705" if healthy else "\u26a0\ufe0f"


def _pending_migrations_actions(*, check: PendingMigrationsCheck) -> list[str]:
    """What to tell an agent about the pending-migrations row — none, one move, or two.

    A machine consumer never learns of a pending migration from a boot: a stale configuration the
    ledger can explain boots with a warning, and the agent CLI silences its own logging before one
    can be emitted. So for an agent this row is not a convenience, it is the only channel.

    Two actions rather than one when a run both migrates some files and leaves others behind,
    which is the ordinary shape on a machine that has drifted: the command is worth running *and*
    something is still owed afterwards, and an agent that only heard the first would stop early.
    """
    actions: list[str] = []
    match check.finding:
        case PendingMigrationsFinding.UP_TO_DATE:
            return actions
        case PendingMigrationsFinding.PENDING:
            migratable = ", ".join(check.migratable_files)
            actions.append(f"Run '{MIGRATE_COMMAND}' to bring these configuration files up to date (it keeps the settings in them): {migratable}")
        case PendingMigrationsFinding.NEEDS_ATTENTION:
            pass
        case PendingMigrationsFinding.UNAVAILABLE:
            actions.append(f"{check.message}. Run '{MIGRATE_COMMAND} --dry-run' to check by hand.")
    if check.attention_files:
        attention = ", ".join(check.attention_files)
        actions.append(
            f"Run '{MIGRATE_COMMAND} --dry-run' to see what these configuration files carry that the migration will not do on its own: {attention}"
        )
    return actions


def _telemetry_action(*, check: TelemetryConfigCheck, config_location: ConfigLocationInfo, migration_already_recommended: bool) -> str | None:
    """What to tell an agent to do about the telemetry finding, or nothing when it is healthy.

    One remedy per finding, because they are genuinely different moves: a missing file is written,
    an out-of-date one is migrated with every setting kept, and a file this build cannot read is
    a person's to edit. The single `pipelex init telemetry` this replaced said the same thing to
    all four, and on the out-of-date one it was destructive advice.

    `migration_already_recommended` is the one case where a finding produces no action: the
    pending-migrations row names the same command and lists this file among the ones it covers, so
    repeating it here would be the same instruction twice at two different scopes.
    """
    match check.finding:
        case TelemetryConfigFinding.HEALTHY:
            return None
        case TelemetryConfigFinding.NOT_FOUND:
            return "Run 'pipelex init telemetry' to write a telemetry configuration"
        case TelemetryConfigFinding.OUT_OF_DATE:
            if migration_already_recommended:
                return None
            return f"Run '{MIGRATE_COMMAND}' to bring telemetry.toml up to date (it keeps the settings in it)"
        case TelemetryConfigFinding.UNPARSEABLE | TelemetryConfigFinding.INVALID:
            return f"Fix {config_location.config_dir}/telemetry.toml: {check.message}"


def _format_doctor_markdown(result: dict[str, Any]) -> str:
    """Format the doctor result dict as markdown with bullet points."""
    all_healthy: bool = result["all_healthy"]
    config_location: dict[str, Any] = result["config_location"]
    checks: dict[str, Any] = result["checks"]

    status_text = f"All healthy {_status_icon(healthy=True)}" if all_healthy else f"Issues found {_status_icon(healthy=False)}"
    location_type = "project-local" if config_location.get("is_project_local") else "global"

    lines: list[str] = [
        "# Pipelex Health Check",
        "",
        f"**Status:** {status_text}",
        f"**Config location:** {config_location['config_dir']} ({location_type})",
    ]

    # Config Files
    config_check = checks["config_files"]
    lines.append(f"\n## Config Files \u2014 {_status_icon(healthy=config_check['healthy'])}\n")
    lines.append(config_check["message"])

    # Configuration Migrations
    migrations_check = checks["pending_migrations"]
    lines.append(f"\n## Configuration Migrations \u2014 {_status_icon(healthy=migrations_check['healthy'])}\n")
    lines.append(migrations_check["message"])
    for file_path in migrations_check["migratable_files"]:
        lines.append(f"- `{file_path}`: out of date")
    for file_path in migrations_check["attention_files"]:
        lines.append(f"- `{file_path}`: needs a look")

    # Telemetry
    telemetry_check = checks["telemetry"]
    lines.append(f"\n## Telemetry \u2014 {_status_icon(healthy=telemetry_check['healthy'])}\n")
    lines.append(telemetry_check["message"])

    # Backend Credentials
    creds_check = checks["backend_credentials"]
    lines.append(f"\n## Backend Credentials \u2014 {_status_icon(healthy=creds_check['healthy'])}\n")
    lines.append(creds_check["message"])
    for backend_entry in creds_check.get("backends", []):
        name = backend_entry["backend_name"]
        if backend_entry["all_credentials_valid"]:
            lines.append(f"- **{name}**: All credentials valid")
        else:
            issues: list[str] = []
            missing = backend_entry.get("missing_vars")
            if missing:
                issues.append(f"missing: {', '.join(missing)}")
            placeholder = backend_entry.get("placeholder_vars")
            if placeholder:
                issues.append(f"placeholder: {', '.join(placeholder)}")
            lines.append(f"- **{name}**: {'; '.join(issues) or 'credentials invalid'}")

    # Models
    models_check = checks["models"]
    models_skipped_flag = models_check.get("skipped", False)
    # Skipped state renders with the warn icon so consumers don't confuse "deferred until
    # config is fixed" with a genuine models failure.
    models_icon = "\u26a0\ufe0f" if models_skipped_flag else _status_icon(healthy=models_check["healthy"])
    lines.append(f"\n## Models \u2014 {models_icon}\n")
    lines.append(models_check["message"])
    for file_entry in models_check.get("backend_files", []):
        name = file_entry["backend_name"]
        if file_entry["is_valid"]:
            lines.append(f"- **{name}** (`{file_entry['file_path']}`): Valid")
        else:
            error_msg = file_entry.get("error_message", "unknown error")
            lines.append(f"- **{name}** (`{file_entry['file_path']}`): Invalid \u2014 {error_msg}")

    # Recommended Actions
    recommended = result.get("recommended_actions", [])
    if recommended:
        lines.append("\n## Recommended Actions\n")
        for index, action in enumerate(recommended, 1):
            lines.append(f"{index}. {action}")

    return "\n".join(lines)


def agent_doctor_cmd(
    global_: Annotated[
        bool,
        typer.Option(
            "--global",
            "-g",
            help="Force checking the global ~/.pipelex/ directory.",
        ),
    ] = False,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Check Pipelex configuration health and output a diagnostic report.

    Unlike the human CLI doctor, this command:
    - Does not offer interactive fixes (diagnostic-only)
    - Includes ``recommended_actions`` for programmatic remediation

    Default output is markdown; use --format json for structured JSON.

    Target directory: auto-detects project .pipelex/ if present, else ~/.pipelex/.
    Use --global/-g to force checking the global ~/.pipelex/ directory.
    """
    set_agent_cli_error_format(error_format or output_format)
    # Process-global logging cutoff, BEFORE setup_doctor_runtime / check_* can trigger
    # any third-party log line.
    silence_logging_for_agent_cli()
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

        # Filesystem-only checks run BEFORE bootstrap: when no --global override is in
        # play, setup_doctor_runtime's load_config materializes ~/.pipelex/ from kit
        # templates as a side effect. Running it first would turn check_config_files into
        # a silent installer on a fresh machine. (The --global path skips materialization
        # — see load_config.)
        config_healthy, config_missing_count, config_message = check_config_files(config_dir=config_dir)
        # No config_dir: this row reports on `pipelex migrate`, which has no --global and walks
        # both configuration directories. See `check_pending_migrations`.
        pending_migrations_check = check_pending_migrations()
        telemetry_check = check_telemetry_config(config_dir=config_dir)
        backends_healthy, backend_credential_reports, backends_message = check_backend_credentials(config_dir=config_dir)

        # check_models requires the hub + log.configure produced by setup_doctor_runtime.
        # When the config is broken (either shape-check fails up front or full validation
        # raises PipelexConfigError inside the bootstrap), we skip running check_models and
        # mark models as skipped — keeping the partial check tuples gathered above so the
        # JSON envelope still reports telemetry/backends instead of degrading to a single
        # error payload.
        models_skipped: bool = False
        models_healthy: bool
        models_message: str
        backend_file_reports: dict[str, BackendFileReport]
        if config_healthy:
            try:
                setup_doctor_runtime(log_config_overrides=AGENT_CLI_STDERR_LOG_FIELDS, config_dir=config_dir)
                # Pin discipline BEFORE check_models. setup_doctor_runtime uses
                # log.configure_if_unset(), which no-ops when a prior process already configured
                # logging (embedded reuse, interleaved tests) — in that case AGENT_CLI_STDERR_LOG_FIELDS
                # never reaches the handler, and any log line check_models emits could land on stdout.
                # apply_agent_cli_output_discipline mutates the existing handler unconditionally via
                # log.redirect_to_stderr, closing that window before any check fires.
                apply_agent_cli_output_discipline()
                models_healthy, models_message, backend_file_reports = check_models(config_dir=config_dir)
            except PipelexConfigError as exc:
                # A config can pass check_config_files's shape check and still fail full validation
                # inside setup_doctor_runtime (e.g. a layered override file). Surface the translated
                # message via the same partial-report shape as the broken-config branch.
                models_skipped = True
                models_healthy = False
                models_message = f"skipped — {exc.message}"
                backend_file_reports = {}
        else:
            models_skipped = True
            models_healthy = False
            models_message = "skipped — fix configuration errors first"
            backend_file_reports = {}
    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any genuinely
        # unexpected failure into the structured error payload. PipelexConfigError is
        # handled by the inner arm above and never reaches here.
        agent_error(f"Health check failed unexpectedly: {exc}", error_type=type(exc).__name__, cause=exc)

    # Pin stdout discipline regardless of bootstrap path (broken-config branch never
    # installed a hub or configured log — the helper guards both internally).
    apply_agent_cli_output_discipline()

    all_healthy = config_healthy and pending_migrations_check.is_healthy and telemetry_check.is_healthy and backends_healthy and models_healthy

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
    recommended_actions.extend(_pending_migrations_actions(check=pending_migrations_check))
    recommended_telemetry_action = _telemetry_action(
        check=telemetry_check,
        config_location=config_location,
        migration_already_recommended=pending_migrations_check.finding.is_repaired_by_migrating,
    )
    if recommended_telemetry_action is not None:
        recommended_actions.append(recommended_telemetry_action)
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
            "pending_migrations": {
                "healthy": pending_migrations_check.is_healthy,
                "finding": str(pending_migrations_check.finding),
                "message": pending_migrations_check.message,
                "migratable_files": pending_migrations_check.migratable_files,
                "attention_files": pending_migrations_check.attention_files,
            },
            "telemetry": {
                "healthy": telemetry_check.is_healthy,
                "finding": str(telemetry_check.finding),
                "message": telemetry_check.message,
            },
            "backend_credentials": {
                "healthy": backends_healthy,
                "message": backends_message,
                "backends": backends_list,
            },
            "models": {
                "healthy": models_healthy,
                "skipped": models_skipped,
                "message": models_message,
                "backend_files": backend_files_list,
            },
        },
    }

    if recommended_actions:
        result["recommended_actions"] = recommended_actions

    match output_format:
        case CliOutputFormat.JSON:
            agent_success(result)
        case CliOutputFormat.MARKDOWN:
            print(_format_doctor_markdown(result))
