"""Content constants for VCS integration test fixtures.

Provides METHODS.toml and .mthds bundle content used by conftest.py
to populate bare git repo fixtures.
"""

from typing import ClassVar


class VCSFixtureData:
    """Constants for building test git repositories."""

    METHODS_TOML: ClassVar[str] = """\
[package]
address = "github.com/mthds-test/vcs-fixture"
version = "1.0.0"
description = "A test fixture package for VCS integration tests"
authors = ["TestBot"]

[exports.vcs_fixture]
pipes = ["vcs_test_pipe"]
"""

    METHODS_TOML_V110: ClassVar[str] = """\
[package]
address = "github.com/mthds-test/vcs-fixture"
version = "1.1.0"
description = "A test fixture package for VCS integration tests (v1.1.0)"
authors = ["TestBot"]

[exports.vcs_fixture]
pipes = ["vcs_test_pipe", "vcs_extra_pipe"]
"""

    BUNDLE_CONTENT: ClassVar[str] = """\
--- domain vcs_fixture
--- pipe vcs_test_pipe
"""

    BUNDLE_CONTENT_V110: ClassVar[str] = """\
--- domain vcs_fixture
--- pipe vcs_test_pipe
--- pipe vcs_extra_pipe
"""


class DependentFixtureData:
    """Constants for a package that depends on vcs-fixture."""

    METHODS_TOML: ClassVar[str] = """\
[package]
address = "github.com/mthds-test/dependent-pkg"
version = "1.0.0"
description = "A dependent test fixture package"
authors = ["TestBot"]

[dependencies]
vcs_fixture = { address = "github.com/mthds-test/vcs-fixture", version = "^1.0.0" }

[exports.dependent]
pipes = ["dependent_pipe"]
"""

    BUNDLE_CONTENT: ClassVar[str] = """\
--- domain dependent
--- pipe dependent_pipe
"""
