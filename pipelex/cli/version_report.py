"""The version handshake both CLIs print for `--version`.

A client of the `pipelex` CLI needs three numbers, not one: the runner's own version,
the MTHDS Protocol version it speaks, and the MTHDS standard version it implements.
The runner version alone cannot answer either question — the three move on independent
cadences by the standard's own versioning rule (`mthds/docs/spec/versioning.md`).

The two numbers that are not pipelex's own are read from the `mthds` package rather
than restated here, so this repo never becomes a second place a version is written.

**This output is a contract, and it is a breaking change to what `--version` printed
before.** A client that drives the CLI as a subprocess should match a line on its label
and read the version after it; one that takes the whole of stdout as a single version
string now holds three lines. The `mthds` runners are that consumer and both still have
to be adapted — the Python one raises rather than reporting a version at all, and the
TypeScript one assigns stdout wholesale — so nothing parses these labels yet.
"""

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from mthds.protocol.protocol import PROTOCOL_VERSION

from pipelex.tools.misc.package_utils import get_package_version

MTHDS_PROTOCOL_LABEL = "mthds-protocol"
"""Label of the MTHDS Protocol line. Part of the CLI's parsed contract — see the module docstring."""

MTHDS_STANDARD_LABEL = "mthds-standard"
"""Label of the MTHDS standard line. Part of the CLI's parsed contract — see the module docstring."""


def version_report_lines(*, program_name: str) -> list[str]:
    """The `--version` output, one `<label> <version>` line per number.

    The shape is a stable contract, not presentation — see the module docstring for what a
    consumer may rely on. The first line keeps the pre-existing `<program> <version>` form,
    so a consumer that matches a version out of the text still works; the two MTHDS lines
    are appended below it, which does break one that consumed stdout whole.

    Args:
        program_name: The console script the caller invoked (`pipelex`, `pipelex-agent`),
            which names the first line.

    Returns:
        The lines to print, in order: the runner version, the protocol version, the
        standard version.
    """
    return [
        f"{program_name} {get_package_version()}",
        f"{MTHDS_PROTOCOL_LABEL} {PROTOCOL_VERSION}",
        f"{MTHDS_STANDARD_LABEL} {MTHDS_STANDARD_VERSION}",
    ]
