"""``pipelex-agent migrate`` — the machine-facing half of the configuration migration.

Same engine and same walk as ``pipelex migrate``; what differs is who reads the answer and how
the run is authorized.

**Nothing is written unless ``--yes`` is passed.** The human command can ask; this one cannot, so
the default is the safe half of that question. The loop an agent runs is therefore
``migrate --dry-run`` to see the plan, then ``migrate --yes`` to apply it — and passing both is
refused rather than resolved, because an agent that asks for one and the other has a bug that a
silent winner would hide.

**The structured fields are the contract.** ``needs_attention`` is the verdict — *this run left
something a person has to decide* — and it is deliberately not "did anything get written": a run
that migrated every file it found has succeeded, and so has a dry run that found nothing blocked.
The exit code and the Markdown rendering are presentation and may change without the contract
changing.

**This command must run when nothing else does**, exactly as its human sibling: no boot, no model
deck, no credentials, no network. A broken configuration is the reason to reach for it.

See ``docs/migration-ledger.md``.
"""

from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import silence_logging_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    set_agent_cli_error_format,
)
from pipelex.cli.commands.migrate_cmd import describe_op
from pipelex.migration.plan import MigrationPlan, MigrationReport
from pipelex.migration.run import config_directories_to_migrate, migrate_config_directories


def agent_migrate_cmd(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report the plan and write nothing. This is already the default; pass it to say so explicitly."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Apply the plan. Without it nothing is written."),
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
    """Migrate this machine's Pipelex configuration files to the current schema.

    Walks the global ``~/.pipelex/`` and the project ``.pipelex/``, replays each configuration
    surface's ledger over every file it claims, and — with ``--yes`` — rewrites what changed,
    backing up each original beside itself.
    """
    set_agent_cli_error_format(error_format or output_format)
    silence_logging_for_agent_cli()
    if dry_run and yes:
        agent_error(
            "--dry-run and --yes contradict each other: one refuses to write, the other authorizes it",
            error_type="ArgumentError",
            exit_code=2,
        )

    config_dirs = config_directories_to_migrate()
    report = migrate_config_directories(config_dirs=config_dirs, dry_run=not yes)
    result = _result_payload(report=report, config_dirs=[str(directory) for directory in config_dirs], applied=yes)
    agent_success_formatted(result, markdown_renderer=_render_markdown, output_format=output_format)
    if report.needs_attention:
        raise typer.Exit(1)


def _result_payload(*, report: MigrationReport, config_dirs: list[str], applied: bool) -> dict[str, Any]:
    """The structured answer: the verdict, the arithmetic, and every plan the run produced.

    Every file the walk visited is here, clean ones included. A report *is* the set of files this
    run looked at, and an agent deciding whether its configuration directory was even reached
    needs the ones that had nothing to say as much as the ones that did.
    """
    return {
        "applied": applied,
        "needs_attention": report.needs_attention,
        "is_clean": report.is_clean,
        "config_dirs": config_dirs,
        "summary": {
            "files_walked": len(report.plans),
            "files_changed": len(report.changed_plans),
            "files_written": len(report.written_plans),
            "files_blocked": len([plan for plan in report.plans if plan.blocked_reason is not None]),
            "entries_blocked": sum(len(plan.blocked) for plan in report.plans),
            "unexplained_paths": sum(len(plan.unexplained) for plan in report.plans),
        },
        "plans": [plan.model_dump(mode="json") for plan in report.plans],
    }


def _render_markdown(result: dict[str, Any]) -> str:
    """The same answer as prose, for an agent reading it rather than parsing it."""
    applied: bool = result["applied"]
    summary: dict[str, Any] = result["summary"]
    config_dirs: list[str] = result["config_dirs"]

    lines: list[str] = ["# Configuration migration", ""]
    if not config_dirs:
        lines += ["No configuration directory was found on this machine — there is nothing to migrate.", ""]
        return "\n".join(lines)

    verdict = "needs attention" if result["needs_attention"] else "nothing left to decide"
    mode = "applied" if applied else "dry run — nothing was written"
    lines += [f"**Mode:** {mode}", f"**Verdict:** {verdict}", "", "**Directories walked:**"]
    lines += [f"- `{directory}`" for directory in config_dirs]
    lines += ["", f"**Files:** {summary['files_walked']} walked, {summary['files_changed']} changed, {summary['files_written']} written."]

    if result["is_clean"]:
        lines += ["", "Every configuration file walked is at the current schema."]
        return "\n".join(lines)

    for plan_dict in result["plans"]:
        plan = MigrationPlan.model_validate(plan_dict)
        if plan.is_clean:
            continue
        lines += ["", f"## `{plan.file_path}`", "", f"Surface: `{plan.surface_id}`", ""]
        lines += _file_lines(plan=plan, applied=applied)
    return "\n".join(lines)


def _file_lines(*, plan: MigrationPlan, applied: bool) -> list[str]:
    if plan.blocked_reason is not None:
        return [f"- **This file could not be processed** (`{plan.blocked_reason}`): {plan.blocked_detail}"]
    lines: list[str] = []
    verb = "Applied" if applied else "Would apply"
    for step in plan.steps:
        lines.append(f"- **{verb} `{step.entry_id}` (schema v{step.to_schema_version}):** {step.title} — {step.description}")
        lines += [f"    - {describe_op(op=op)}" for op in step.applied_ops]
    for blocked in plan.blocked:
        lines.append(f"- **Blocked `{blocked.entry_id}` (schema v{blocked.to_schema_version}, `{blocked.reason}`):** {blocked.detail}")
        lines += [f"    - already applied: {describe_op(op=op)}" for op in blocked.applied_ops]
        if blocked.narrowed_paths:
            lines.append(f"    - check by hand: {', '.join(f'`{path}`' for path in blocked.narrowed_paths)}")
        if blocked.guidance:
            lines += [f"    - {line}" for line in blocked.guidance.splitlines() if line.strip()]
    for unexplained in plan.unexplained:
        lines.append(f"- **Unexplained path `{unexplained.path}`:** {unexplained.note}")
    if plan.backup_path is not None:
        lines.append(f"- Backup of the original: `{plan.backup_path}`")
    return lines
