"""Guards the published documentation against citations its readers cannot follow.

`docs/` is the MkDocs `docs_dir` published at docs.pipelex.com. A workspace ledger id or a `wip/` path
means something to a contributor with the private workspace checked out and nothing to anyone reading
the site, so the page states the fact in plain words or leaves the pointer out. Ids and paths stay
welcome in code comments, commit messages and pull request bodies.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Anchored on `tests/` by name rather than by a parent count — a depth index is silently wrong from the
#: workspace root, which holds a sibling `pipelex/` checkout (see `test_hub_layering_guard.py`).
REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

DOCS_DIR = REPO_ROOT / "docs"

LEDGER_ID_PATTERN = re.compile(r"\bL-\d{6}-[0-9a-f]{6}\b")
# A `wip/` path segment, but not one that merely ends a longer name such as `mthds-wip/`.
WIP_PATH_PATTERN = re.compile(r"(?<![\w-])wip/")

TEXT_SUFFIXES = frozenset({".md", ".html", ".css", ".txt", ".yml", ".yaml"})


class TestDocsCiteNothingPrivate:
    def test_published_docs_carry_no_ledger_id_and_no_wip_path(self) -> None:
        """Every page under docs/ reads without the private workspace: no ledger item id, no `wip/` path."""
        doc_files = sorted(path for path in DOCS_DIR.rglob("*") if path.is_file() and path.suffix in TEXT_SUFFIXES)
        assert doc_files, f"no documentation files found under {DOCS_DIR}"
        offending_lines: list[str] = []
        for doc_file in doc_files:
            for line_number, line in enumerate(doc_file.read_text(encoding="utf-8").splitlines(), start=1):
                if LEDGER_ID_PATTERN.search(line) or WIP_PATH_PATTERN.search(line):
                    offending_lines.append(f"{doc_file.relative_to(REPO_ROOT)}:{line_number}: {line.strip()[:160]}")
        assert not offending_lines, (
            "docs/ is published on docs.pipelex.com, whose readers cannot open the workspace ledger or wip/: "
            "state the fact in plain words or drop the pointer.\n" + "\n".join(offending_lines)
        )
