"""Guards the published documentation against citations its readers cannot follow.

`docs/` is the MkDocs `docs_dir` published at docs.pipelex.com. A workspace ledger id, a `wip/` path or a
document at the root of the private workspace (its `docs/specs/`, its ledger, its conventions) means
something to a contributor with the workspace checked out and nothing to anyone reading the site, so the
page states the fact in plain words, links a public page that states it, or leaves the pointer out. Ids and
paths stay welcome in code comments, commit messages and pull request bodies.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Anchored on `tests/` by name rather than by a parent count — a depth index is silently wrong from the
#: workspace root, which holds a sibling `pipelex/` checkout (see `test_hub_layering_guard.py`).
REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

DOCS_DIR = REPO_ROOT / "docs"

PRIVATE_REFERENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "ledger item id": re.compile(r"\bL-\d{6}-[0-9a-f]{6}\b"),
    # A path segment, but not one that merely ends a longer name (`mthds-wip/`) or sits inside a URL.
    "wip/ path": re.compile(r"(?<![\w./-])wip/"),
    # This repository has no docs/specs/, so the path can only name the workspace's.
    "workspace spec path": re.compile(r"(?<![\w./-])docs/specs/"),
    "workspace reference": re.compile(r"\bworkspace[- ](root|ledger|convention)s?\b", re.IGNORECASE),
}

TEXT_SUFFIXES = frozenset({".md", ".html", ".css", ".txt", ".yml", ".yaml"})


class TestDocsCiteNothingPrivate:
    def test_published_docs_cite_nothing_in_the_private_workspace(self) -> None:
        """Every page under docs/ reads without the private workspace: no ledger id, no `wip/` path, no workspace-root document."""
        doc_files = sorted(path for path in DOCS_DIR.rglob("*") if path.is_file() and path.suffix in TEXT_SUFFIXES)
        assert doc_files, f"no documentation files found under {DOCS_DIR}"
        offending_lines: list[str] = []
        for doc_file in doc_files:
            for line_number, line in enumerate(doc_file.read_text(encoding="utf-8").splitlines(), start=1):
                for label, pattern in PRIVATE_REFERENCE_PATTERNS.items():
                    if pattern.search(line):
                        offending_lines.append(f"{doc_file.relative_to(REPO_ROOT)}:{line_number}: {label}: {line.strip()[:160]}")
        assert not offending_lines, (
            "docs/ is published on docs.pipelex.com, whose readers cannot open the private workspace: "
            "state the fact in plain words, link a public page, or drop the pointer.\n" + "\n".join(offending_lines)
        )
