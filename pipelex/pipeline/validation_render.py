"""Public, non-CLI Markdown rendering for validation results.

This is the public home of ``format_validate_markdown`` — lifted out of the
agent CLI (``cli/agent_cli/commands/validate/_output_helpers.py``) so it can be
imported by other surfaces (notably ``pipelex-api``'s ``/validate`` route, which
attaches an opt-in ``rendered_markdown`` extra) WITHOUT pulling in Typer / the
CLI internals. The agent CLI keeps using it for its ``--format markdown`` valid
path, so the local-CLI and API-runner Markdown share one source of truth and
cannot drift.

``format_validate_markdown`` renders the **valid-arm** result;
``render_invalid_verdict_markdown`` renders the **invalid-arm** verdict from its
problem items, the ``errors`` a host answers in the view of whoever asked, so
the Markdown says no more than the structured items it presents.

``format_validation_error_items_markdown`` is the markdown sibling of the human
``display_validation_error_items`` (``cli/error_handlers.py``): it renders typed
:class:`ValidationErrorItem`s as category-grouped prose with per-item ``💡
Suggested fix`` lines. It backs the agent ``validate`` failure surface and the
agent ``fix`` still-invalid surface so the prose an agent reads mirrors the
human panel and cannot drift. ``build_fix_command`` is the shared builder for the copy-pasteable
``<executable> fix bundle <path>`` footer, used by both the human and agent
``validate`` surfaces so the ``-L`` / ``--allow-signatures`` echo cannot drift.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.error_codes import error_code_spec, parse_error_code
from pipelex.interpreter_hub import resolve_library_dirs
from pipelex.pipeline.fixes.applicability import is_safe_fix_for_load_scope, is_target_in_write_scope
from pipelex.suggested_fix import FixSafety, SuggestedFix
from pipelex.tools.misc.string_utils import count_with_noun, pascal_case_to_sentence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mthds.protocol.problem.models import ProblemItem


def format_validate_markdown(result: dict[str, Any]) -> str:
    """Render a validation result dict as agent-readable markdown.

    Covers the success-path shape produced by the ``validate`` core helpers:
    ``validated_pipes`` (a list of ``{pipe_ref, status}``), ``total_pipes``,
    and an optional ``bundle_path``. ``validate bundle --graph`` / ``--view``
    also merge ``graph_files`` / ``graphspec`` into the result — those are
    surfaced too so markdown mode does not silently drop them — or, for a
    method's folder with no single pipe to draw, ``graph_unavailable``, the
    reason no graph was drawn.

    Args:
        result: The JSON-mode result dict for the validation.

    Returns:
        A markdown string for stdout.
    """
    lines: list[str] = ["# Validation passed", ""]

    bundle_path = result.get("bundle_path")
    if bundle_path:
        lines += [f"**Bundle:** `{bundle_path}`", ""]

    validated_pipes: list[dict[str, Any]] = result.get("validated_pipes") or []
    total_pipes = result.get("total_pipes", len(validated_pipes))
    lines.append(f"Validated {count_with_noun(count=total_pipes, singular='pipe')}:")
    lines.append("")
    for entry in validated_pipes:
        lines.append(f"- `{entry.get('pipe_ref')}` — {entry.get('status')}")

    # Runnability verdict — gated on key *presence*, not truthiness. Only the bundle-validate
    # surfaces put `pending_signatures` in the result; `validate all` / `validate pipe` omit the key,
    # so they get no verdict (claiming runnability there would be misleading). Present-and-empty is a
    # complete bundle (runnable); present-and-non-empty still has forward declarations to implement.
    if "pending_signatures" in result:
        pending_signatures: list[str] = result["pending_signatures"] or []
        if pending_signatures:
            pending_count = len(pending_signatures)
            if pending_count == 1:
                verdict = "⚠️ This method is NOT yet runnable — 1 pipe is still a `PipeSignature` placeholder and must be implemented before running:"
            else:
                verdict = (
                    f"⚠️ This method is NOT yet runnable — {pending_count} pipes are still "
                    "`PipeSignature` placeholders and must be implemented before running:"
                )
            # Verdict line is emitted immediately above the verbatim "Pending signatures" heading —
            # downstream consumers rely on that exact ordering (see agent_cli/CLAUDE.md).
            lines += [
                "",
                verdict,
                "",
                f"## Pending signatures ({pending_count})",
                "",
            ]
            for pending_ref in pending_signatures:
                lines.append(f"- `{pending_ref}`")
        else:
            lines += [
                "",
                (
                    "✅ All pipes are concretely implemented — no `PipeSignature` placeholders remain. "
                    "Strict validation will pass; this method is runnable."
                ),
            ]

    # Advisory lints (e.g. the useless-`!` lint) — informational: the bundle IS valid.
    warnings: list[dict[str, Any]] = result.get("warnings") or []
    if warnings:
        lines += ["", f"## Warnings ({len(warnings)})", ""]
        for warning in warnings:
            lines.append(f"- **{warning.get('error_type') or warning.get('category')}** — {warning.get('message')}")

    graph_files = result.get("graph_files")
    if isinstance(graph_files, dict):
        lines += ["", "## Graph files", ""]
        for graph_label, graph_path in cast("dict[str, Any]", graph_files).items():
            lines.append(f"- **{graph_label}:** `{graph_path}`")

    if "graphspec" in result:
        lines += ["", "_A GraphSpec (structured graph JSON) is included — use `--format json` to retrieve it._"]

    graph_unavailable = result.get("graph_unavailable")
    if graph_unavailable:
        lines += ["", "## Graph", "", str(graph_unavailable)]

    return "\n".join(lines)


def render_invalid_verdict_markdown(*, items: Sequence[ProblemItem], message: str) -> str:
    """Render an invalid validation verdict (the InvalidReport arm) as agent-readable markdown, from its problem items.

    The items are the verdict's ``errors`` in the view of whoever asked, the caller's leaving out what only the
    operator reads, so the Markdown a host attaches beside them (the opt-in ``rendered_markdown`` of ``/validate``)
    says what they say and no more: each item numbered under its code's title, with its code, where it is, its
    sentence, its suggestions and its suggested fix, labelled with its safety. A ``# Validation failed`` heading frames
    it. It never reads a validation item's own message, which the operator's tools render and which a caller's view
    does not carry.

    ``rendered_markdown`` is presentation, never the contract: the machine consumer branches on the JSON ``is_valid``
    and ``errors`` fields (see workspace ``CLAUDE.md`` § "Surface output conventions"). No CLI-command footer is emitted
    here: an API consumer applies fixes through the structured ``suggested_fix`` operations.

    Args:
        items: The verdict's problem items, in the view of the reader the Markdown is for.
        message: The verdict's sentence, shown when it holds no item.

    Returns:
        A markdown string.
    """
    lines: list[str] = ["# Validation failed", ""]
    if not items:
        # Defensive: the structured-info invariant guarantees a non-empty `errors` on every produced invalid verdict,
        # so this branch should be unreachable, but a verdict that somehow carries no item still shows its sentence.
        lines.append(message)
    for item_index, item in enumerate(items, 1):
        lines += _render_problem_item_markdown(item=item, index=item_index)
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_problem_item_markdown(*, item: ProblemItem, index: int) -> list[str]:
    """Render one problem item as prose: its code's title and its code, where it is, its sentence, suggestions and fix."""
    code = parse_error_code(item.code)
    title = error_code_spec(code).title if code is not None else item.code
    lines: list[str] = [f"{index}. **{title}** (`{item.code}`)"]
    location = item.location
    if location is not None:
        if location.pipe:
            lines.append(f"   - Pipe: `{location.pipe}`")
        if location.input:
            lines.append(f"   - Input: `{location.input}`")
        if location.field:
            lines.append(f"   - Field: `{location.field}`")
        if location.file:
            position = f"{location.file}:{location.line}" if location.line is not None else location.file
            lines.append(f"   - File: `{position}`")
    lines.append(f"   - {item.detail}")
    for suggestion in item.suggestions or []:
        lines.append(f"   - {suggestion}")
    if item.suggested_fix is not None:
        safety = FixSafety(str(item.suggested_fix.effective_safety))
        lines.append(f"   - 💡 {fix_safety_label(safety=safety)}: {item.suggested_fix.description}")
    return lines


def validation_item_title(*, item: ValidationErrorItem) -> str:
    """The heading of one validation item: its ``error_type`` in words, or ``Validation Error`` without one.

    Shared by the human panel and the markdown so both name an item alike. The stage codes are
    snake_case (``unknown_model`` → ``Unknown Model``); the dry-run code is an exception's name
    (``DryRunError`` → ``Dry Run Error``).
    """
    if not item.error_type:
        return "Validation Error"
    error_type = str(item.error_type)
    if "_" in error_type or error_type.islower():
        return error_type.replace("_", " ").title()
    return pascal_case_to_sentence(error_type).title()


def _markdown_category_header(category: ValidationErrorCategory) -> str:
    """The section heading for one validation-error category — markdown sibling of the human header."""
    match category:
        case ValidationErrorCategory.BLUEPRINT_VALIDATION:
            return "Blueprint validation errors"
        case ValidationErrorCategory.PIPE_FACTORY:
            return "Pipe factory errors"
        case ValidationErrorCategory.PIPE_VALIDATION:
            return "Pipe validation errors"
        case ValidationErrorCategory.DRY_RUN:
            return "Dry run errors"


def suggested_fix_label(*, fix: SuggestedFix) -> str:
    """The label a rendered suggested fix opens with, saying whether it may be applied without asking.

    A safe fix is a plain ``Suggested fix``: ``pipelex fix bundle`` applies it on its own. An unsafe
    one, such as ``rename-model``, whose close match by name can still be a different model, says it is
    unsafe and needs confirming, because ``pipelex fix bundle`` never applies it and the person or agent
    reading the line decides. The word is the wire's own ``safety`` value, the one the TypeScript clients
    show. Shared by the human panel (``cli/error_handlers.py``) and the markdown prose here, so every
    surface labels a fix the same way.
    """
    return fix_safety_label(safety=fix.safety)


def fix_safety_label(*, safety: FixSafety) -> str:
    """The label a rendered suggested fix of this safety opens with (:func:`suggested_fix_label`)."""
    match safety:
        case FixSafety.SAFE:
            return "Suggested fix"
        case FixSafety.UNSAFE:
            return "Suggested fix (unsafe, confirm before applying)"


def _render_error_item_markdown(item: ValidationErrorItem, *, index: int) -> list[str]:
    """Render one structured item as prose: humanized title, identity fields, message, fix, locators.

    Markdown sibling of the human ``_display_validation_error_item`` — same fields in the same
    order, emitting ``**bold**`` / backticks instead of Rich markup.
    """
    lines: list[str] = [f"{index}. **{validation_item_title(item=item)}**"]
    if item.pipe_code:
        lines.append(f"   - Pipe: `{item.pipe_code}`")
    if item.concept_code:
        lines.append(f"   - Concept: `{item.concept_code}`")
    if item.domain_code:
        lines.append(f"   - Domain: `{item.domain_code}`")
    if item.field_name:
        lines.append(f"   - Field: `{item.field_name}`")
    if item.missing_concept_code:
        lines.append(f"   - Missing concept: `{item.missing_concept_code}`")
    if item.missing_pipe_code:
        lines.append(f"   - Missing pipe: `{item.missing_pipe_code}`")
    if item.declared_concepts:
        declared = ", ".join(f"`{concept_code}`" for concept_code in item.declared_concepts)
        lines.append(f"   - Declared concepts: {declared}")
    if item.variable_names:
        variables = ", ".join(f"`{variable_name}`" for variable_name in item.variable_names)
        lines.append(f"   - Variables: {variables}")
    lines.append(f"   - {item.message}")
    if item.suggested_fix is not None:
        lines.append(f"   - 💡 {suggested_fix_label(fix=item.suggested_fix)}: {item.suggested_fix.description}")
    if item.field_path:
        lines.append(f"   - Path: `{item.field_path}`")
    if item.source:
        lines.append(f"   - Source: `{item.source}`")
    return lines


def format_validation_error_items_markdown(items: list[ValidationErrorItem]) -> str:
    """Render structured validation-error items grouped by category as agent-readable markdown.

    The markdown sibling of the human ``display_validation_error_items``
    (``cli/error_handlers.py``): same category grouping, same per-item identity fields + message
    + ``💡 Suggested fix`` line, emitting markdown instead of Rich markup. Consumes the typed
    items produced by the shared ``build_validation_error_items`` builder — the same source the
    human panel and the structured wire draw from — so the prose an agent reads cannot drift from
    what a human sees. Returns only the grouped items block (no heading, no footer); callers wrap
    it with the surface-specific framing.

    Args:
        items: The structured validation-error items to render, in builder order.

    Returns:
        A markdown string: one ``## <Category>`` section per populated category, each holding
        numbered prose items (one per failing pipe in the ``dry_run`` section).
    """
    items_by_category: dict[ValidationErrorCategory, list[ValidationErrorItem]] = {}
    for item in items:
        items_by_category.setdefault(item.category, []).append(item)

    lines: list[str] = []
    for category in ValidationErrorCategory:
        category_items = items_by_category.get(category, [])
        if not category_items:
            continue
        if lines:
            lines.append("")
        lines += [f"## {_markdown_category_header(category)}", ""]
        # Every category, dry run included, renders numbered items: a dry-run item is located on its
        # failing pipe like any other, so it names the pipe, the domain and the source.
        for error_index, item in enumerate(category_items, 1):
            lines += _render_error_item_markdown(item, index=error_index)
            lines.append("")

    return "\n".join(lines).rstrip()


def build_fix_command(*, executable: str, bundle_path: Path, library_dirs: list[Path] | None = None, allow_signatures: bool = False) -> str:
    """Build the copy-pasteable ``<executable> fix bundle <path>`` command for a fix-aware footer.

    Shared by the human ``validate`` footer (``executable="pipelex"``) and the agent ``validate``
    footer (``executable="pipelex-agent"``) so the suggested command reproduces the same write
    scope — the ``-L`` library dirs and ``--allow-signatures`` leniency — identically on both
    surfaces. ``shlex.join`` keeps a path with spaces a single argument when the footer is pasted.

    Args:
        executable: The CLI binary name (``pipelex`` or ``pipelex-agent``).
        bundle_path: The bundle file / pipeline directory being validated.
        library_dirs: The ``-L/--library-dir`` values of the invocation, echoed so the fix runs
            with the same library scope.
        allow_signatures: Whether the invocation accepted ``PipeSignature`` placeholders; echoed so
            the fix preserves the same leniency.

    Returns:
        The shell-safe command string.
    """
    command_parts = [executable, "fix", "bundle", str(bundle_path)]
    for library_dir in library_dirs or []:
        command_parts.extend(["-L", str(library_dir)])
    if allow_signatures:
        command_parts.append("--allow-signatures")
    return shlex.join(command_parts)


def count_applicable_fixes(
    items: list[ValidationErrorItem],
    *,
    bundle_path: Path,
    library_dirs: list[Path] | None,
) -> int:
    """Count safe fixes the displayed command is authorized and able to apply.

    A method's folder always loads as a library directory, so its load is never a single file's, and that is decided
    without asking the interpreter hub for its default directories: a folder whose tree is refused before the boot is
    reported, with this count, while no hub exists.
    """
    is_single_file = not bundle_path.is_dir() and not resolve_library_dirs(library_dirs)[0]
    entry_path = bundle_path.resolve()
    writable_dirs = [library_dir.resolve() for library_dir in library_dirs] if library_dirs is not None else []
    applicable_count = 0
    for item in items:
        fix = item.suggested_fix
        if fix is None or not is_safe_fix_for_load_scope(fix, is_single_file=is_single_file):
            continue
        if fix.source is None:
            target_path = entry_path
        else:
            target_path = Path(fix.source).resolve()
        if is_target_in_write_scope(target_path, entry_path=entry_path, writable_dirs=writable_dirs):
            applicable_count += 1
    return applicable_count
