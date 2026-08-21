"""Smoke-test for the `validate --all` CLI path: a directory of bundles validates and dry-runs.

The directory is assembled from the corpus's **valid** entries rather than pointed at a tree on
disk. That used to be `pipelex/`, the package directory, chosen to avoid the conflicting fixtures
under `tests/` — but the package's only `.mthds` files are the corpus's, so the test has been
sweeping the corpus for a while without saying so, and the moment the corpus grew deliberately
invalid entries it started failing on bundles that are *supposed* to fail.

Selecting by `validity` states the intent the path expression only implied, and keeps the test
correct as the corpus grows in either direction. The per-entry guarantee — that a valid entry
validates and an invalid one fails with exactly its declared error — is not this test's job; it
belongs to the corpus entry-validation gate, which is stronger. What this covers is the CLI's
whole-directory path: many bundles merged into one library, then dry-run together.
"""

import shutil
from pathlib import Path

from pipelex.cli.commands.validate._validate_core import do_validate_all_libraries_and_dry_run
from pipelex.test_extras.mthds_corpus.loader import iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryValidity


class TestValidateCommand:
    def test_validate_all(self, tmp_path: Path):
        copied = 0
        for entry in iter_entries(validity=EntryValidity.VALID):
            shutil.copytree(entry.directory, tmp_path / entry.name)
            copied += 1
        # An empty directory validates vacuously, so the assembly is pinned rather than assumed:
        # a selection that silently returned nothing would leave this test green over no bundles.
        assert copied, "The corpus yielded no valid entries, so this test would validate an empty directory"

        do_validate_all_libraries_and_dry_run(library_dirs=[tmp_path])
