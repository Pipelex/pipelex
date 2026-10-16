"""The report of a function names migration, as Markdown for a person or an agent to read."""

from pipelex.migration.function_names import FunctionNamesMigration
from pipelex.pipe_operators.func.function_name import FUNCTION_NAMES_MIGRATION_COMMAND


def format_function_names_markdown(*, migration: FunctionNamesMigration, directory: str, is_dry_run: bool) -> str:
    """The migration's report: what it rewrote, or would rewrite in a dry run, and what it left for the author."""
    verb = "would rewrite" if is_dry_run else "rewrote"
    lines: list[str] = [f"# Function names of the method at {directory}", ""]
    if not migration.rewrites and not migration.marker_removals and not migration.unresolved:
        lines.append("Every PipeFunc step already names its function by import path: nothing to migrate.")
        return "\n".join(lines)

    if migration.rewrites:
        lines.extend([f"The migration {verb} these function names as import paths:", ""])
        for rewrite in migration.rewrites:
            lines.append(f"- `{rewrite.bundle}`, pipe `{rewrite.pipe_code}`: `{rewrite.flat_name}` → `{rewrite.import_path}`")
        lines.append("")
    if migration.marker_removals:
        drop = "would drop" if is_dry_run else "dropped"
        lines.extend([f"The migration {drop} the registration name of these `@pipe_func(...)` markers, which take no argument now:", ""])
        for removal in migration.marker_removals:
            lines.append(f"- `{removal.module}`, function `{removal.function}`, registered as `{removal.registered_name}`")
        lines.append("")
    if migration.unresolved:
        lines.extend(["These function names are left as they are, for you to decide:", ""])
        for unresolved in migration.unresolved:
            where = f"`{unresolved.bundle}`, pipe `{unresolved.pipe_code}`" if unresolved.pipe_code is not None else f"`{unresolved.bundle}`"
            name = f" `{unresolved.flat_name}`" if unresolved.flat_name is not None else ""
            lines.append(f"- {where}{name}: {unresolved.reason}")
            for candidate in unresolved.candidates:
                lines.append(f"    - candidate `{candidate}`")
        lines.append("")
    if is_dry_run and migration.has_changes:
        lines.append(f"Nothing was written. Run `{FUNCTION_NAMES_MIGRATION_COMMAND} {directory}` to write these changes.")
    return "\n".join(lines).rstrip() + "\n"
