"""Guards the published documentation against citations its readers cannot follow.

`docs/` is the MkDocs `docs_dir` published at docs.pipelex.com. A workspace ledger id, a `wip/` path or a
document in the private workspace (an interface spec in its internal `conformance` repo, its ledger, its
conventions) means something to a contributor with the workspace checked out and nothing to anyone reading
the site, so the page states the fact in plain words, links a public page that states it, or leaves the
pointer out. Ids and paths stay welcome in code comments, commit messages and pull request bodies.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Anchored on `tests/` by name rather than by a parent count — a depth index is silently wrong from the
#: workspace root, which holds a sibling `pipelex/` checkout (see `test_hub_layering_guard.py`).
REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

DOCS_DIR = REPO_ROOT / "docs"

#: A `pymdownx.snippets` include, whose path resolves against `base_path: .` in `mkdocs.yml`, the repo root.
#: The file it names is published as part of the page, so it is held to the same rule.
SNIPPET_INCLUDE_PATTERN = re.compile(r'^\s*--8<--\s+"([^"]+)"')

#: Read on the raw line, so an id is caught inside a URL too.
PRIVATE_ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "ledger item id": re.compile(r"\bL-\d{6}-[0-9a-f]{6}\b"),
    "workspace reference": re.compile(r"\bworkspace[- ](root|ledger|convention)s?\b", re.IGNORECASE),
}

#: A URL is somebody else's path space (`https://opentelemetry.io/docs/specs/…`), so the path patterns read the
#: line with its URLs blanked out.
URL_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)

#: A path segment, whether bare, backticked or behind a relative link (`../../wip/`), but not one that merely
#: ends a longer name (`mthds-wip/`).
PRIVATE_PATH_PATTERNS: dict[str, re.Pattern[str]] = {
    "wip/ path": re.compile(r"(?<![\w-])wip/"),
    # This repository has no docs/specs/, so the path can only name the workspace's, which now holds nothing
    # but a pointer to the conformance repo.
    "workspace spec path": re.compile(r"(?<![\w-])docs/specs/"),
    # Nor has it a conformance/ directory, so the path can only name the internal conformance repo, whose
    # specs/ holds the interface specs that moved out of the workspace's docs/specs/.
    "conformance repo path": re.compile(r"(?<![\w-])conformance/"),
}

TEXT_SUFFIXES = frozenset({".md", ".html", ".css", ".txt", ".yml", ".yaml"})


def published_files() -> list[Path]:
    """Every text file under docs/, plus every file a docs page pulls in with a snippet include."""
    doc_files = {path for path in DOCS_DIR.rglob("*") if path.is_file() and path.suffix in TEXT_SUFFIXES}
    included_files: set[Path] = set()
    for doc_file in doc_files:
        for line in doc_file.read_text(encoding="utf-8").splitlines():
            if include := SNIPPET_INCLUDE_PATTERN.match(line):
                included_files.add(REPO_ROOT / include.group(1))
    return sorted(doc_files | included_files)


def private_references(*, line: str) -> list[str]:
    """The labels of the private references the line carries."""
    url_free_line = URL_PATTERN.sub("", line)
    return [label for label, pattern in PRIVATE_ID_PATTERNS.items() if pattern.search(line)] + [
        label for label, pattern in PRIVATE_PATH_PATTERNS.items() if pattern.search(url_free_line)
    ]


class TestDocsCiteNothingPrivate:
    def test_published_docs_cite_nothing_in_the_private_workspace(self) -> None:
        """Every published page reads without the private workspace: no ledger id, no `wip/` path, no workspace or `conformance` spec."""
        doc_files = published_files()
        assert doc_files, f"no documentation files found under {DOCS_DIR}"
        offending_lines: list[str] = []
        for doc_file in doc_files:
            assert doc_file.is_file(), f"a docs page includes {doc_file.relative_to(REPO_ROOT)}, which does not exist"
            for line_number, line in enumerate(doc_file.read_text(encoding="utf-8").splitlines(), start=1):
                offending_lines.extend(
                    f"{doc_file.relative_to(REPO_ROOT)}:{line_number}: {label}: {line.strip()[:160]}" for label in private_references(line=line)
                )
        assert not offending_lines, (
            "docs/ is published on docs.pipelex.com, whose readers cannot open the private workspace: "
            "state the fact in plain words, link a public page, or drop the pointer.\n" + "\n".join(offending_lines)
        )

    def test_private_path_patterns_catch_relative_links_and_skip_urls(self) -> None:
        """A relative link out of docs/ is the likeliest way a page cites the workspace; another site's URL is not a citation."""
        for cited in (
            "[d](../../wip/foo.md)",
            "./wip/x",
            "`wip/x`",
            "[s](../../../docs/specs/corpus.md)",
            "`docs/specs/x.md`",
            "[s](../../../conformance/specs/mthds-test-corpus.md)",
            "`conformance/specs/x.md`",
        ):
            assert private_references(line=cited), cited
        for clean in (
            "mthds-wip/x",
            "mthds-conformance/x",
            "## Conformance tiers",
            "https://opentelemetry.io/docs/specs/semconv/",
            "https://example.com/wip/y",
            "https://example.com/conformance/specs/z",
        ):
            assert not private_references(line=clean), clean
