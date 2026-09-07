"""The `--version` handshake: three numbers, on both CLIs, in a shape a client can parse.

The output is a contract rather than presentation — a client drives the CLI as a subprocess
and turns these lines into a protocol `VersionInfo`. So the assertions here pin the contract
itself: the labels as literal strings, and the output as *exactly* the three lines. Bounding
the output is the half that matters for a machine consumer, since anything printed ahead of
the handshake (a logo banner, a warning) breaks it just as surely as a missing line.
"""

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from mthds.protocol.protocol import PROTOCOL_VERSION
from typer.testing import CliRunner

from pipelex.cli._cli import app as pipelex_app
from pipelex.cli.agent_cli._agent_cli import app as agent_app
from pipelex.cli.version_report import MTHDS_PROTOCOL_LABEL, MTHDS_STANDARD_LABEL, version_report_lines
from pipelex.tools.misc.package_utils import get_package_version


class TestVersionHandshake:
    """The shared builder, and what each CLI's `--version` actually prints."""

    def test_labels_are_the_literal_strings_a_client_parses(self) -> None:
        """Pinned as literals on purpose: reading them from the constants under test
        would let a rename pass, and a rename is exactly the break that reaches a client.
        """
        assert MTHDS_PROTOCOL_LABEL == "mthds-protocol"
        assert MTHDS_STANDARD_LABEL == "mthds-standard"

    def test_reports_the_three_numbers_in_order(self) -> None:
        lines = version_report_lines(program_name="pipelex")
        assert lines == [
            f"pipelex {get_package_version()}",
            f"{MTHDS_PROTOCOL_LABEL} {PROTOCOL_VERSION}",
            f"{MTHDS_STANDARD_LABEL} {MTHDS_STANDARD_VERSION}",
        ]

    def test_program_name_names_the_first_line_only(self) -> None:
        lines = version_report_lines(program_name="pipelex-agent")
        assert lines[0] == f"pipelex-agent {get_package_version()}"
        assert lines[1:] == version_report_lines(program_name="pipelex")[1:]

    def test_bare_cli_prints_exactly_the_handshake(self) -> None:
        result = CliRunner().invoke(pipelex_app, ["--version"])
        assert result.exit_code == 0
        assert result.output.splitlines() == version_report_lines(program_name="pipelex")

    def test_agent_cli_prints_exactly_the_handshake(self) -> None:
        result = CliRunner().invoke(agent_app, ["--version"])
        assert result.exit_code == 0
        assert result.output.splitlines() == version_report_lines(program_name="pipelex-agent")

    def test_no_banner_or_other_noise_precedes_the_first_line(self) -> None:
        """The logo banner does print ahead of output on other paths, and anything ahead of
        the handshake breaks a machine consumer as surely as a missing line does.
        """
        for app, program_name in ((pipelex_app, "pipelex"), (agent_app, "pipelex-agent")):
            output = CliRunner().invoke(app, ["--version"]).output
            assert output.startswith(f"{program_name} ")
            assert len(output.splitlines()) == 3
