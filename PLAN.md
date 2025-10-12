# Goal

Add a `kit` command group that:

1. Exports each `pipelex.kit/agents/*.md` to **Cursor** as `.cursor/rules/*.mdc` (adds YAML front-matter from `index.toml`).
2. Builds a **merged single-file rules block** from ordered fragments (with `demote=1`) and inserts/updates it in targets (`AGENTS.md`, `CLAUDE.md`, etc.) using **marker spans**.
   All parsing/merging via **markdown-parser-py**; config via **TOML → dict** (`toml_utils`) → **Pydantic v2** models.

---

# Package layout (as agreed)

```
pipelex/kit/
  __init__.py
  index.toml
  agents/
    pytest_standards.md
    python_standards.md
    run_pipelines.md
    write_pipelex.md
  configs/
    ... (as provided)
  migrations/
    ... (optional)
```

---

# Pydantic v2 models (dict → object via `model_validate`)

```python
# pipelex/kit/index_models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class AgentsMerge(BaseModel):
    order: List[str]
    demote: int = 1

class CursorFileOverride(BaseModel):
    front_matter: Dict[str, Any] = Field(default_factory=dict)

class CursorSpec(BaseModel):
    front_matter: Dict[str, Any] = Field(default_factory=dict)
    files: Dict[str, CursorFileOverride] = Field(default_factory=dict)

class Target(BaseModel):
    id: str
    path: str
    strategy: str  # "merge" (for now)
    marker_begin: str
    marker_end: str
    parent: Optional[str] = None

class KitIndex(BaseModel):
    meta: Dict[str, Any] = Field(default_factory=dict)
    agents: AgentsMerge
    cursor: CursorSpec
    targets: List[Target]
```

**Load `index.toml` using your utils:**

```python
# pipelex/kit/index_loader.py
from pipelex.tools.misc.toml_utils import load_toml_from_path, TomlError
from importlib.resources import files
from .index_models import KitIndex

def load_index() -> KitIndex:
    path = files("pipelex.kit") / "index.toml"
    data = load_toml_from_path(str(path))
    return KitIndex.model_validate(data)
```

---

# CLI integration (Typer)

Add a **`kit`** sub-app under your existing CLI:

```python
# pipelex/cli/commands/kit_cmd.py
import typer
from pathlib import Path
from typing_extensions import Annotated
from pipelex.kit.index_loader import load_index
from pipelex.kit.paths import get_agents_dir  # small helper shown below
from pipelex.kit.cursor_export import export_cursor_rules
from pipelex.kit.targets_update import build_merged_rules, update_targets

kit_app = typer.Typer(help="Manage kit assets: export Cursor rules and merge agent docs")

@kit_app.command("sync")
def sync(
    repo_root: Annotated[Path, typer.Option("--repo-root", dir_okay=True, writable=True)] = Path("."),
    cursor: Annotated[bool, typer.Option("--cursor/--no-cursor")] = True,
    single_files: Annotated[bool, typer.Option("--single-files/--no-single-files")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    diff: Annotated[bool, typer.Option("--diff")] = False,
    backup: Annotated[str | None, typer.Option("--backup")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
):
    idx = load_index()
    agents_dir = get_agents_dir()

    if cursor:
        export_cursor_rules(agents_dir, repo_root / ".cursor" / "rules", idx, dry_run=dry_run)

    if single_files:
        merged_md = build_merged_rules(agents_dir, idx)  # ordered + demoted
        update_targets(repo_root, merged_md, idx.targets, dry_run=dry_run, diff=diff, backup=backup, force=force)
```

Wire it into your main CLI:

```python
# in your main cli module
from pipelex.cli.commands.kit_cmd import kit_app
app.add_typer(kit_app, name="kit", help="Manage kit assets")
```

---

# Core helpers

## Paths

```python
# pipelex/kit/paths.py
from importlib.resources import files
from typing import Any
from importlib.abc import Traversable

def get_kit_root() -> Traversable:
    return files("pipelex.kit")

def get_agents_dir() -> Traversable:
    return get_kit_root() / "agents"
```

## Cursor export (.md → .mdc with YAML front matter)

```python
# pipelex/kit/cursor_export.py
from typing import Iterable
from pathlib import Path
import textwrap
import yaml  # pyyaml (MIT)
from importlib.abc import Traversable
from .index_models import KitIndex
from pipelex.tools.misc.toml_utils import TomlError  # (for symmetry if needed)

def _iter_agent_files(agents_dir: Traversable) -> Iterable[tuple[str, str]]:
    for child in agents_dir.iterdir():
        if child.name.endswith(".md") and child.is_file():
            yield child.name, child.read_text(encoding="utf-8")

def _front_matter_for(name: str, idx: KitIndex) -> dict:
    base = dict(idx.cursor.front_matter)
    key = name.removesuffix(".md")
    if key in idx.cursor.files:
        base |= idx.cursor.files[key].front_matter
    return base

def export_cursor_rules(agents_dir: Traversable, out_dir: Path, idx: KitIndex, dry_run: bool=False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, body in _iter_agent_files(agents_dir):
        fm = _front_matter_for(fname, idx)
        yaml_block = "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip() + "\n---\n"
        mdc = yaml_block + body
        out_path = out_dir / (fname.removesuffix(".md") + ".mdc")
        if dry_run:
            typer.echo(f"[DRY] write {out_path}")
        else:
            out_path.write_text(mdc, encoding="utf-8")
```

## Merging for single-file targets (markdown-parser-py)

```python
# pipelex/kit/targets_update.py
from dataclasses import dataclass
from pathlib import Path
from importlib.abc import Traversable
from typing import List
import difflib
import typer

from markdown_parser_py import Doc  # replace with actual import names
from markdown_parser_py import parse as md_parse, render as md_render  # adjust to real API

from .index_models import KitIndex, Target
from .markers import find_span, wrap, replace_span
from pipelex.tools.misc.toml_utils import load_toml_from_path  # (not strictly needed here)

def _read_agent_file(agents_dir: Traversable, name: str) -> str:
    return (agents_dir / name).read_text(encoding="utf-8")

def _demote(doc: Doc, n: int) -> Doc:
    # Walk headings and +n to their level (implementation per markdown-parser-py API)
    # pseudo:
    # for h in doc.headings(): h.level += n
    return doc

def build_merged_rules(agents_dir: Traversable, idx: KitIndex) -> str:
    parts: List[str] = []
    for name in idx.agents.order:
        md = _read_agent_file(agents_dir, name)
        d = md_parse(md)
        d = _demote(d, idx.agents.demote)
        parts.append(md_render(d).rstrip())
    return ("\n\n".join(parts)).strip() + "\n"

def _insert_block_with_ast(target_md: str, block_md: str, parent: str | None) -> str:
    # Parse both; locate parent heading (if any) or choose heuristic (after first H1 or end)
    # Attach block as a new section. Return rendered string.
    tdoc = md_parse(target_md or "")
    bdoc = md_parse(block_md)
    # ... attach via library’s attach API (level handling already demoted)
    return md_render(tdoc)

def _diff(before: str, after: str, path: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=path, tofile=path))

def update_targets(repo_root: Path, merged_rules: str, targets: List[Target],
                   dry_run: bool, diff: bool, backup: str | None, force: bool) -> None:
    for t in targets:
        p = repo_root / t.path
        before = p.read_text(encoding="utf-8") if p.exists() else ""
        span = find_span(before, t.marker_begin, t.marker_end)

        if span:
            after_block = wrap(t.marker_begin, t.marker_end, merged_rules)
            after = replace_span(before, span, after_block)
        else:
            inserted = _insert_block_with_ast(before, merged_rules, t.parent)
            after = inserted if inserted.endswith("\n") else inserted + "\n"
            # wrap only the inserted region — simplest approach is to wrap merged_rules before insert
            # or insert markers during AST attach (implementation detail)

        if dry_run:
            typer.echo(f"[DRY] update {p}")
            if diff:
                typer.echo(_diff(before, after, str(p)))
        else:
            if backup and p.exists():
                (p.with_suffix(p.suffix + backup)).write_text(before, encoding="utf-8")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(after, encoding="utf-8")
```

## Markers

```python
# pipelex/kit/markers.py
def find_span(text: str, begin: str, end: str):
    s = text.find(begin)
    if s == -1: return None
    e = text.find(end, s)
    if e == -1: return None
    e += len(end)
    return (s, e)

def wrap(begin: str, end: str, md: str) -> str:
    return f"{begin}\n{md.rstrip()}\n{end}"

def replace_span(text: str, span: tuple[int,int], replacement: str) -> str:
    s, e = span
    return text[:s] + replacement + text[e:]
```

---

# Behavior rules (quick)

* **Cursor**: overwrite `.cursor/rules/*.mdc` each run (we own them).
* **Single-file**: only mutate content within our markers; if absent, **insert via AST** and add markers.
* **Demote before concat** (per `index.toml`).
* Preserve front-matter/encoding/line endings.
* `--dry-run` prints plan; `--diff` shows unified diff; `--backup` writes `*.bak`.

---

# Exit codes

* `0` success / no changes
* `1` failures (I/O, parse, invalid index, write blocked)
* `2` ambiguous parent resolution (if you choose to enforce)

This plugs directly into your existing CLI, uses your TOML loader + Pydantic v2, and scopes the implementation clearly for another SWE to take over.
