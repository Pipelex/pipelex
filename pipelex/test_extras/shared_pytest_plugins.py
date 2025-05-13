# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.runtime_manager import RunMode, runtime_manager


@pytest.fixture(scope="session", autouse=True)
def set_run_mode():
    runtime_manager.set_run_mode(run_mode=RunMode.UNIT_TEST)


@pytest.fixture(scope="session")
def manage_pipelex_libraries():
    LibraryConfig.export_libraries(overwrite=False)
    yield
    # TODO: make it safe to erase/replace standard libraries in client projects without touching custom stuff
    # LibraryConfig.remove_libraries()
