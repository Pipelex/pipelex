from pathlib import Path

import pytest

from pipelex.cli.commands.validate_cmd import do_validate_all_libraries_and_dry_run
from pipelex.libraries.domain.exceptions import DomainLibraryError
from pipelex.libraries.exceptions import LibraryLoadingError


class TestValidateCommand:
    @pytest.mark.xfail(
        reason=(
            "Fixture files in refactoring/test-package-fixtures/ cause failures when loaded alongside the main library: "
            "LibraryLoadingError from intentional visibility violations (scoring.internal_score_normalizer not exported), "
            "or DomainLibraryError from duplicate 'scoring' domain colliding with test fixtures — "
            "which error occurs depends on file discovery order (platform-dependent)"
        ),
        raises=(LibraryLoadingError, DomainLibraryError),
    )
    def test_validate_all(self):
        do_validate_all_libraries_and_dry_run(library_dirs=[Path()])
