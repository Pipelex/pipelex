"""Typer sub-app for drift contracts: `pipelex-dev drift plan|check|ack`.

Wires the pure core to the git adapter; this module owns presentation only.
`plan` prints Markdown (its consumer is an agent), `check` prints the CI-gate
report, `ack` runs verify commands then records the review.
"""

from __future__ import annotations

import shlex
import subprocess  # noqa: S404
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated

import typer
from rich.markup import escape

from pipelex.cli.dev_cli.commands.drift.core import (
    ContractPlanPacket,
    DriftIssue,
    DriftIssueKind,
    build_plan_packets,
    compute_current_digest,
    find_issues,
    match_files,
)
from pipelex.cli.dev_cli.commands.drift.exceptions import DriftAckError, DriftError
from pipelex.cli.dev_cli.commands.drift.git_adapter import (
    get_git_user_name,
    get_repo_toplevel,
    read_staged_files,
    read_unstaged_modified,
    read_untracked,
)
from pipelex.cli.dev_cli.commands.drift.models import (
    ACKS_DIR_RELATIVE,
    DriftAck,
    DriftContract,
    ack_file_path,
    load_all_acks,
    load_manifest,
    save_ack,
)
from pipelex.hub import get_console

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from rich.console import Console

VERIFY_COMMAND_TIMEOUT_SECONDS = 900

drift_app = typer.Typer(no_args_is_help=True)


def _resolve_repo_root(repo_root: Path | None) -> Path:
    return repo_root if repo_root is not None else get_repo_toplevel()


def _issue_message(issue: DriftIssue) -> str:
    match issue.kind:
        case DriftIssueKind.DEAD_TRIGGER_PATTERN:
            return f"trigger pattern '{issue.detail}' matches no tracked file"
        case DriftIssueKind.DEAD_REVIEW_TARGET:
            return f"review target '{issue.detail}' matches no tracked file"
        case DriftIssueKind.MISSING_ACK:
            return "no ack recorded — initial review required"
        case DriftIssueKind.ORPHAN_ACK:
            return f"ack file '{ACKS_DIR_RELATIVE / (issue.contract_id + '.toml')}' has no matching contract in drift.toml"
        case DriftIssueKind.ACK_CONTRACT_MISMATCH:
            return f"ack contract field '{issue.detail}' does not match its filename stem"
        case DriftIssueKind.DIGEST_MISMATCH:
            return "trigger content or contract definition changed since last ack"


def drift_check_cmd(*, quiet: bool = False, repo_root: Path | None = None) -> None:
    """The CI gate: validate the manifest and every ack against the current index. Exits 1 on any issue."""
    console = get_console()
    resolved_root = _resolve_repo_root(repo_root)
    manifest = load_manifest(resolved_root)
    staged_oids = read_staged_files(resolved_root)
    acks = load_all_acks(resolved_root)
    issues = find_issues(manifest, staged_oids=staged_oids, acks=acks)

    if not issues:
        if quiet:
            console.print("[green]✓ Drift check: PASSED[/green]")
        else:
            console.print()
            console.print("[green]✓ Drift check: PASSED[/green] — every contract is fulfilled")
            console.print()
        return

    console.print()
    console.print("[bold red]✗ Drift check: FAILED[/bold red]")
    console.print()
    for issue in issues:
        console.print(f"  [red]✗[/red] [cyan]{issue.contract_id}[/cyan]: {escape(_issue_message(issue))}")
    console.print()
    if any(issue.kind.is_manifest_rot for issue in issues):
        console.print("  Dead patterns are manifest rot: edit drift.toml first.")
    console.print("  To see open contracts and how to fulfill them,")
    console.print("  run `make drift-plan`")
    console.print()
    sys.exit(1)


def _render_packet_markdown(packet: ContractPlanPacket) -> str:
    lines: list[str] = [f"## Open contract: {packet.contract_id}", "", packet.contract.description, ""]
    previous_ack = packet.previous_ack
    if previous_ack is None:
        lines.append("**Trigger files** (no previous ack — initial review required):")
    else:
        ack_date = previous_ack.reviewed_at.split("T")[0]
        lines.append(f'**Trigger changes since last ack** (by {previous_ack.reviewed_by}, {ack_date}, "{previous_ack.rationale}"):')
    lines.append("")
    for path in packet.diff.added:
        lines.append(f"- added: {path}")
    for path in packet.diff.removed:
        lines.append(f"- removed: {path}")
    for path in packet.diff.modified:
        lines.append(f"- modified: {path}")
    if packet.diff.is_empty:
        lines.append("- (no trigger-file changes — the contract definition itself changed)")
    lines.extend(["", "**Review targets:**", ""])
    lines.extend(f"- {target}" for target in packet.contract.review)
    if packet.contract.verify_commands:
        lines.extend(["", "**Verify commands (run by ack):**", ""])
        lines.extend(f"- {command}" for command in packet.contract.verify_commands)
    ack_invocation = f'make drift-ack CONTRACT={packet.contract_id} RATIONALE="…"'
    lines.extend(
        [
            "",
            "**To fulfill:** review the targets against the trigger changes, update what is stale,",
            f"stage the trigger files (`git add`), then run `{ack_invocation}`",
        ]
    )
    return "\n".join(lines)


def drift_plan_cmd(contract_id: str | None = None, *, repo_root: Path | None = None) -> None:
    """List open contracts as Markdown packets (the consumer is an agent fulfilling them)."""
    resolved_root = _resolve_repo_root(repo_root)
    manifest = load_manifest(resolved_root)
    if contract_id is not None and contract_id not in manifest.contracts:
        known_ids = ", ".join(manifest.contracts)
        msg = f"Unknown contract '{contract_id}' — known contracts: {known_ids}"
        raise DriftError(msg)
    staged_oids = read_staged_files(resolved_root)
    acks = load_all_acks(resolved_root)
    packets = build_plan_packets(manifest, staged_oids=staged_oids, acks=acks)
    if contract_id is not None:
        packets = [packet for packet in packets if packet.contract_id == contract_id]
        if not packets:
            typer.echo(f"Contract '{contract_id}' is fulfilled — nothing to review.")
            return
    if not packets:
        typer.echo("All drift contracts are fulfilled — nothing to review.")
        return
    rendered = "\n\n".join(_render_packet_markdown(packet) for packet in packets)
    typer.echo(rendered)


def _run_verify_commands(commands: Sequence[str], *, repo_root: Path, console: Console) -> None:
    """Run each verify command (shlex argv, no shell, cwd=repo root, env inherited); first failure aborts."""
    for command in commands:
        argv = shlex.split(command)
        if not argv:
            msg = f"Empty verify command in contract definition: {command!r}"
            raise DriftAckError(msg)
        console.print(f"  Running verify command: [cyan]{escape(command)}[/cyan]")
        try:
            result = subprocess.run(  # noqa: S603
                argv,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=VERIFY_COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = f"Verify command not found: '{argv[0]}' — ack aborted, nothing written"
            raise DriftAckError(msg) from exc
        except subprocess.TimeoutExpired as exc:
            msg = f"Verify command timed out after {VERIFY_COMMAND_TIMEOUT_SECONDS}s: '{command}' — ack aborted, nothing written"
            raise DriftAckError(msg) from exc
        if result.returncode != 0:
            if result.stdout.strip():
                console.print(escape(result.stdout))
            if result.stderr.strip():
                console.print(escape(result.stderr))
            msg = f"Verify command failed (exit {result.returncode}): '{command}' — ack aborted, nothing written"
            raise DriftAckError(msg)


def _warn_uncovered_working_tree(contract: DriftContract, *, repo_root: Path, console: Console) -> None:
    """Warn when working-tree state lags the index: the ack covers staged content only."""
    unstaged_matched = match_files(read_unstaged_modified(repo_root), patterns=contract.triggers, exclude=contract.exclude)
    for path in unstaged_matched:
        console.print(f"[yellow]⚠[/yellow] trigger file has unstaged modifications: {escape(path)}")
        console.print("  The ack covers its staged content — `git add` it first if the edit should be covered.")
    untracked_matched = match_files(read_untracked(repo_root), patterns=contract.triggers, exclude=contract.exclude)
    for path in untracked_matched:
        console.print(f"[yellow]⚠[/yellow] untracked file matches triggers: {escape(path)}")
        console.print("  Untracked files are not covered until staged (`git add`).")


def drift_ack_cmd(contract_id: str, *, rationale: str, reviewed_by_override: str | None = None, repo_root: Path | None = None) -> None:
    """Run the contract's verify commands, then record the ack from the current index state."""
    console = get_console()
    resolved_root = _resolve_repo_root(repo_root)
    manifest = load_manifest(resolved_root)
    contract = manifest.contracts.get(contract_id)
    if contract is None:
        known_ids = ", ".join(manifest.contracts)
        msg = f"Unknown contract '{contract_id}' — known contracts: {known_ids}"
        raise DriftAckError(msg)
    if not rationale.strip():
        msg = "An ack requires a non-empty --rationale: it is the on-the-record review decision"
        raise DriftAckError(msg)
    reviewed_by = reviewed_by_override or get_git_user_name(resolved_root)
    if reviewed_by is None:
        msg = "Cannot resolve the reviewer identity: set `git config user.name` or pass --by"
        raise DriftAckError(msg)

    _run_verify_commands(contract.verify_commands, repo_root=resolved_root, console=console)

    staged_oids = read_staged_files(resolved_root)
    digest_result = compute_current_digest(contract, contract_id=contract_id, staged_oids=staged_oids)
    _warn_uncovered_working_tree(contract, repo_root=resolved_root, console=console)

    ack = DriftAck(
        contract=contract_id,
        digest=digest_result.digest,
        reviewed_by=reviewed_by,
        reviewed_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        rationale=rationale,
        trigger_files=digest_result.trigger_files,
    )
    save_ack(ack, repo_root=resolved_root)
    ack_path = ack_file_path(resolved_root, contract_id=contract_id)
    console.print(f"[green]✓[/green] Ack recorded for [cyan]{contract_id}[/cyan] at {ack_path.relative_to(resolved_root)}")
    console.print("  Commit the ack file together with the change it covers.")


@drift_app.command("plan", help="Show open drift contracts and how to fulfill them (Markdown output)")
def plan_command(
    contract: Annotated[str | None, typer.Argument(help="Contract id — show the full packet for this contract only")] = None,
) -> None:
    """Show open drift contracts and how to fulfill them."""
    drift_plan_cmd(contract)


@drift_app.command("check", help="CI gate: validate the manifest and every ack against the current index")
def check_command(
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Single line on success; failures always print in full")] = False,
) -> None:
    """Validate drift contracts; exit non-zero when any contract is open or the manifest rotted."""
    drift_check_cmd(quiet=quiet)


@drift_app.command("ack", help="Run the contract's verify commands, then record the review ack")
def ack_command(
    contract: Annotated[str, typer.Argument(help="Contract id to acknowledge")],
    rationale: Annotated[str, typer.Option("--rationale", "-r", help="The on-the-record review decision (required)")],
    by: Annotated[str | None, typer.Option("--by", help="Reviewer identity (default: git config user.name)")] = None,
) -> None:
    """Record a fulfilled review for one contract."""
    drift_ack_cmd(contract, rationale=rationale, reviewed_by_override=by)
