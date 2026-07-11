"""Drift Hunt Stage 0 — mechanical pre-screen over the in-scope docs pages.

Throwaway campaign tooling (see TODOS.md). Deterministic checks only; every hit is a
*suspect* for human/agent triage, not a verdict. Checks:

  paths      referenced repo file paths exist (docs/cookbook/ resolves against ../pipelex-cookbook too, per D3)
  config     TOML sections/keys shown in config-looking fenced blocks exist in pipelex/pipelex.toml (or .pipelex/pipelex.toml)
  cli        pipelex / pipelex-dev / pipelex-agent / plxt commands and flags exist in the real --help surfaces
  make       `make <target>` mentions exist in the Makefile
  toml       fenced ```toml blocks parse
  python     fenced ```python blocks compile (ast.parse)
  links      internal markdown links resolve to existing files

Usage:  .venv/bin/python wip/drift-hunt/prescreen.py > wip/drift-hunt/prescreen-raw.md

Run from the repo root. Output: one Markdown report of FAIL rows grouped by check,
each row = page · claim · evidence, plus per-section/per-check counts.
"""
# ruff: noqa: INP001

from __future__ import annotations

import ast
import re
import subprocess  # noqa: S404
import sys
import tomllib
from collections import Counter
from pathlib import Path

REPO_ROOT = Path.cwd()
DOCS_ROOT = REPO_ROOT / "docs"
COOKBOOK_ROOT = (REPO_ROOT / ".." / "pipelex-cookbook").resolve()

# Mirrors wip/drift-hunt/inventory.md (D2 scope + pending-confirmation pages).
EXCLUDED_DIRS = {"errors", "configuration", "overrides"}
EXCLUDED_SUBDIRS = {("tools", "cli")}
EXCLUDED_PAGES = {
    "docs/changelog.md",
    "docs/contributing.md",
    "docs/CODE_OF_CONDUCT.md",
    "docs/setup/gateway-models.md",
}

CLI_NAMES = ["pipelex", "pipelex-agent", "pipelex-dev", "plxt"]
VENV_BIN = REPO_ROOT / ".venv" / "bin"

PATHY_EXTENSIONS = (
    ".py", ".md", ".toml", ".mthds", ".json", ".txt", ".yml", ".yaml",
    ".csv", ".html", ".css", ".sh", ".plx", ".lock", ".png", ".jpg", ".jpeg", ".svg", ".webp",
)
PATHY_PREFIXES = ("pipelex/", "docs/", "tests/", ".pipelex/", "wip/", ".drift/", ".claude/", "derived/")
PLACEHOLDER_MARKERS = ("<", ">", "{", "}", "*", "…", "path/to", "your_", "my_", "...")

FENCE_RE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
TOML_SECTION_RE = re.compile(r"^\s*\[\[?([A-Za-z0-9_.\-\"]+)\]\]?\s*$")
TOML_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_\-]+)\s*=")


def find_pages() -> list[Path]:
    pages: list[Path] = []
    for page in sorted(DOCS_ROOT.rglob("*.md")):
        rel = page.relative_to(REPO_ROOT)
        parts = rel.parts[1:]  # drop leading "docs"
        if parts[0] in EXCLUDED_DIRS:
            continue
        if len(parts) > 2 and (parts[0], parts[1]) in EXCLUDED_SUBDIRS:
            continue
        if str(rel) in EXCLUDED_PAGES:
            continue
        pages.append(page)
    return pages


def split_fences(text: str) -> tuple[list[tuple[str, str, int]], str]:
    """Return (fenced blocks as [(lang, body, start_line)], text with fences blanked)."""
    blocks: list[tuple[str, str, int]] = []
    out_lines: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = FENCE_RE.match(lines[index])
        if match:
            lang = match.group(1).lower()
            body_lines: list[str] = []
            start = index + 1
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                body_lines.append(lines[index])
                index += 1
            blocks.append((lang, "\n".join(body_lines), start + 1))
            out_lines.extend([""] * (index - start + 2))
            index += 1
        else:
            out_lines.append(lines[index])
            index += 1
    return blocks, "\n".join(out_lines)


# ---------- CLI surface harvest ----------

BOX_ROW_RE = re.compile(r"^[│|]\s+(\S+)")
PLAIN_CMD_RE = re.compile(r"^  ([a-z][a-z0-9_-]*)\s{2,}")
OPTION_TOKEN_RE = re.compile(r"(--[A-Za-z0-9][A-Za-z0-9-]*|-[A-Za-z])\b")


def run_help(argv: list[str]) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            [*argv, "--help"], capture_output=True, text=True, timeout=60, check=False,
            env={"PATH": f"{VENV_BIN}:/usr/bin:/bin", "TERM": "dumb", "NO_COLOR": "1", "COLUMNS": "200", "HOME": str(Path.home())},
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout + result.stderr


def parse_help(help_text: str) -> tuple[set[str], set[str]]:
    """Extract (subcommand names, option flags) from typer/rich or clap help output."""
    commands: set[str] = set()
    options: set[str] = set()
    section = ""
    for line in help_text.splitlines():
        lowered = line.lower()
        if "─ commands ─" in lowered or lowered.strip() in {"commands:", "subcommands:"}:
            section = "commands"
            continue
        if "─ options ─" in lowered or lowered.strip() in {"options:", "arguments:"}:
            section = "options"
            continue
        if line.startswith("╰") or (not line.strip() and section == "commands" and commands):
            section = ""
            continue
        if section == "commands":
            match = BOX_ROW_RE.match(line) or PLAIN_CMD_RE.match(line)
            if match:
                name = match.group(1)
                if re.fullmatch(r"[a-z][a-z0-9_-]*", name):
                    commands.add(name)
        options.update(OPTION_TOKEN_RE.findall(line))
    return commands, options


def harvest_cli(cli: str) -> dict[str, set[str]]:
    """Map 'sub command path' -> option flags, recursing through subcommands."""
    surface: dict[str, set[str]] = {}
    queue: list[list[str]] = [[]]
    seen: set[str] = set()
    while queue:
        path = queue.pop(0)
        key = " ".join(path)
        if key in seen:
            continue
        seen.add(key)
        help_text = run_help([str(VENV_BIN / cli), *path])
        if not help_text:
            continue
        commands, options = parse_help(help_text)
        surface[key] = options
        for command in commands:
            queue.append([*path, command])
    return surface


def harvest_make_targets() -> set[str]:
    targets: set[str] = set()
    makefile = REPO_ROOT / "Makefile"
    for line in makefile.read_text().splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:", line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


def load_config_paths() -> tuple[set[str], set[str]]:
    """Dotted section paths and dotted key paths from pipelex/pipelex.toml + .pipelex/pipelex.toml."""
    sections: set[str] = set()
    keys: set[str] = set()

    def walk(table: dict, prefix: str) -> None:
        for name, value in table.items():
            dotted = f"{prefix}.{name}" if prefix else name
            if isinstance(value, dict):
                sections.add(dotted)
                walk(value, dotted)
            else:
                keys.add(dotted)

    for toml_path in [REPO_ROOT / "pipelex" / "pipelex.toml", REPO_ROOT / ".pipelex" / "pipelex.toml"]:
        if toml_path.is_file():
            walk(tomllib.loads(toml_path.read_text()), "")
    return sections, keys


# ---------- checks ----------

class Row:
    def __init__(self, page: str, check: str, claim: str, evidence: str) -> None:
        self.page = page
        self.check = check
        self.claim = claim
        self.evidence = evidence


def looks_like_repo_path(token: str) -> bool:
    if "://" in token or token.startswith(("http", "#", "$")):
        return False
    if token.startswith(("./", "../", "/")):
        return False  # page-relative link targets belong to the links check; leading "/" is a site/web path
    if any(marker in token for marker in PLACEHOLDER_MARKERS):
        return False
    if "/" not in token:
        return False
    if not (token.endswith(PATHY_EXTENSIONS) or token.startswith(PATHY_PREFIXES)):
        return False
    return re.fullmatch(r"[A-Za-z0-9_./\-]+", token) is not None


def check_paths(page: Path, page_rel: str, tokens: set[str], rows: list[Row]) -> int:
    checked = 0
    is_cookbook = page_rel.startswith("docs/cookbook/")
    for token in sorted(tokens):
        if not looks_like_repo_path(token):
            continue
        # Unanchored tokens (no known repo prefix) are usually example-project files
        # (`generated/structures.py`, `my_project/main.mthds`) — only cookbook pages, whose
        # whole point is referencing the sibling examples repo, get those checked.
        anchored = token.startswith(PATHY_PREFIXES)
        if not anchored and not is_cookbook:
            continue
        checked += 1
        exists = (REPO_ROOT / token).exists() or (page.parent / token).exists()
        if not exists and is_cookbook:
            exists = (COOKBOOK_ROOT / token).exists()
        if not exists:
            where = "repo nor ../pipelex-cookbook" if is_cookbook else "repo (nor page-relative)"
            rows.append(Row(page_rel, "paths", token, f"no such file in {where}"))
    return checked


def check_config_blocks(page_rel: str, blocks: list[tuple[str, str, int]], sections: set[str], keys: set[str], rows: list[Row]) -> int:
    top_levels = {section.split(".")[0] for section in sections}
    checked = 0
    for lang, body, start_line in blocks:
        if lang != "toml":
            continue
        current: str | None = None
        relevant = False
        for offset, line in enumerate(body.splitlines()):
            section_match = TOML_SECTION_RE.match(line)
            if section_match:
                current = section_match.group(1).strip('"')
                relevant = current.split(".")[0] in top_levels
                if relevant:
                    checked += 1
                    if current not in sections:
                        rows.append(Row(page_rel, "config", f"[{current}]", f"section not in pipelex.toml (line {start_line + offset})"))
                continue
            key_match = TOML_KEY_RE.match(line)
            if key_match and relevant and current is not None and current in sections:
                checked += 1
                dotted = f"{current}.{key_match.group(1)}"
                if dotted not in keys and dotted not in sections:
                    rows.append(Row(page_rel, "config", f"{dotted}", f"key not in pipelex.toml [{current}] (line {start_line + offset})"))
    return checked


SHELL_PREFIX_RE = re.compile(r"^(\$\s+|sudo\s+|uv run\s+|uvx\s+|\.venv/bin/|[A-Z_]+=\S+\s+)+")


def iter_cli_invocations(blocks: list[tuple[str, str, int]], prose: str) -> list[str]:
    lines: list[str] = []
    for lang, body, _ in blocks:
        if lang in {"bash", "shell", "sh", "console", "zsh", ""}:
            merged = body.replace("\\\n", " ")
            lines.extend(merged.splitlines())
    lines.extend(CODE_SPAN_RE.findall(prose))
    invocations: list[str] = []
    for raw in lines:
        line = SHELL_PREFIX_RE.sub("", raw.strip())
        first = line.split(" ", 1)[0] if line else ""
        if first in CLI_NAMES or first == "make":
            invocations.append(line.split("#", 1)[0].split("|", 1)[0].split("&&", 1)[0].strip())
    return invocations


def check_cli(page_rel: str, invocations: list[str], surfaces: dict[str, dict[str, set[str]]], make_targets: set[str], rows: list[Row]) -> int:
    checked = 0
    for invocation in invocations:
        tokens = invocation.split()
        if not tokens:
            continue
        cli = tokens[0]
        if cli == "make":
            for target in tokens[1:]:
                if "=" in target or target.startswith("-"):
                    break
                checked += 1
                if target not in make_targets:
                    rows.append(Row(page_rel, "make", invocation, f"no Makefile target '{target}'"))
            continue
        surface = surfaces.get(cli)
        if surface is None:
            continue
        path: list[str] = []
        flags: list[str] = []
        for token in tokens[1:]:
            if token.startswith("-"):
                flags.append(token.split("=", 1)[0])
            elif not flags and " ".join([*path, token]) in surface:
                path.append(token)
            elif not flags and not path and re.fullmatch(r"[a-z][a-z0-9_-]*", token):
                # first non-flag token is not a known subcommand: suspicious unless it's an arg to the root
                checked += 1
                rows.append(Row(page_rel, "cli", invocation, f"'{cli} {token}' is not a known subcommand"))
                break
            else:
                break  # positional arg — stop descending
        else:
            known_options = surface.get(" ".join(path), set())
            for flag in flags:
                if not flag.startswith("--"):
                    continue  # short flags too noisy to verify
                checked += 1
                if flag not in known_options:
                    rows.append(Row(page_rel, "cli", invocation, f"'{flag}' not in `{cli} {' '.join(path)} --help`"))
    return checked


def check_fenced_blocks(page_rel: str, blocks: list[tuple[str, str, int]], rows: list[Row]) -> int:
    checked = 0
    for lang, body, start_line in blocks:
        if lang == "toml":
            checked += 1
            try:
                tomllib.loads(body)
            except tomllib.TOMLDecodeError as exc:
                rows.append(Row(page_rel, "toml", f"fenced toml at line {start_line}", str(exc)))
        elif lang == "python":
            checked += 1
            try:
                ast.parse(body)
            except SyntaxError as exc:
                rows.append(Row(page_rel, "python", f"fenced python at line {start_line}", f"{exc.msg} (block line {exc.lineno})"))
    return checked


def check_links(page: Path, page_rel: str, prose: str, rows: list[Row]) -> int:
    checked = 0
    for target in LINK_RE.findall(prose):
        if target.startswith(("http://", "https://", "mailto:", "#", "{")):
            continue
        checked += 1
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (page.parent / clean).resolve()
        if not resolved.exists():
            rows.append(Row(page_rel, "links", target, "target does not exist"))
    return checked


def main() -> int:
    pages = find_pages()
    print(f"<!-- prescreen over {len(pages)} pages; generated by wip/drift-hunt/prescreen.py -->", file=sys.stderr)

    surfaces = {cli: harvest_cli(cli) for cli in CLI_NAMES}
    for cli, surface in surfaces.items():
        print(f"<!-- harvested {cli}: {len(surface)} command paths -->", file=sys.stderr)
    make_targets = harvest_make_targets()
    sections, keys = load_config_paths()

    rows: list[Row] = []
    checked_counts: Counter[str] = Counter()
    for page in pages:
        page_rel = str(page.relative_to(REPO_ROOT))
        text = page.read_text()
        blocks, prose = split_fences(text)

        tokens: set[str] = set(CODE_SPAN_RE.findall(prose))
        for _, body, _ in blocks:
            tokens.update(body.split())
        tokens.update(LINK_RE.findall(prose))

        checked_counts["paths"] += check_paths(page, page_rel, tokens, rows)
        checked_counts["config"] += check_config_blocks(page_rel, blocks, sections, keys, rows)
        checked_counts["cli+make"] += check_cli(page_rel, iter_cli_invocations(blocks, prose), surfaces, make_targets, rows)
        checked_counts["toml+python"] += check_fenced_blocks(page_rel, blocks, rows)
        checked_counts["links"] += check_links(page, page_rel, prose, rows)

    print("# Drift Hunt — Stage 0 pre-screen raw hits\n")
    print(f"Pages scanned: {len(pages)}. Claims checked: {dict(checked_counts)}. FAIL rows below: {len(rows)}.\n")
    by_check: dict[str, list[Row]] = {}
    for row in rows:
        by_check.setdefault(row.check, []).append(row)
    for check in sorted(by_check):
        print(f"## {check} ({len(by_check[check])})\n")
        for row in by_check[check]:
            print(f"- `{row.page}` · `{row.claim}` — {row.evidence}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
