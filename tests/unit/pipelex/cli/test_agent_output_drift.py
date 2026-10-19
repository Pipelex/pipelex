import ast
from pathlib import Path

import pipelex.cli.agent_cli

# The functions that report a problem and take the command's own members as keyword arguments.
_PROBLEM_REPORTERS: frozenset[str] = frozenset({"agent_error", "agent_argument_error", "agent_file_error"})

# The members of the retired envelope, which a problem carries under its own names (code, domain, retry, next_step,
# errors, diagnostics) or not at all.
_RETIRED_ENVELOPE_MEMBERS: frozenset[str] = frozenset(
    {"error", "error_type", "error_domain", "error_code", "error_category", "retryable", "hint", "validation_errors", "error_source"}
)


# The parameters of ``client.argument_invalid``, which ``agent_argument_error`` takes.
_ARGUMENT_REFUSAL_PARAMS: frozenset[str] = frozenset({"argument", "reason"})


def _reporter_name(*, call: ast.Call) -> str | None:
    match call.func:
        case ast.Name(id=name):
            return name
        case ast.Attribute(attr=name):
            return name
        case _:
            return None


class TestAgentOutputDrift:
    def test_no_call_site_passes_a_member_of_the_retired_envelope(self) -> None:
        """No agent CLI call site passes a member of the envelope the problem replaced.

        ``agent_error`` takes a command's own members as ``**extra``, so a leftover ``error_type=`` or ``hint=`` would
        not fail: it would ride beside the problem under a name consumers used to read as the envelope's.
        """
        package_dir = Path(pipelex.cli.agent_cli.__file__).parent
        offenders: list[str] = []
        for source_file in sorted(package_dir.rglob("*.py")):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or _reporter_name(call=node) not in _PROBLEM_REPORTERS:
                    continue
                reporter = _reporter_name(call=node)
                for keyword in node.keywords:
                    if keyword.arg in _RETIRED_ENVELOPE_MEMBERS:
                        offenders.append(f"{source_file.relative_to(package_dir)}:{node.lineno} passes {keyword.arg}=")
                    elif reporter == "agent_error" and keyword.arg in _ARGUMENT_REFUSAL_PARAMS:
                        # The parameters of client.argument_invalid, passed to agent_error, ride as members of the
                        # command's own beside a problem with no code of theirs: the call meant agent_argument_error.
                        offenders.append(f"{source_file.relative_to(package_dir)}:{node.lineno} passes {keyword.arg}= to agent_error")
        assert not offenders, (
            "These calls pass a member of the envelope the problem replaced; name a code (code=, params=) or let the "
            f"cause's own problem speak: {offenders}"
        )
