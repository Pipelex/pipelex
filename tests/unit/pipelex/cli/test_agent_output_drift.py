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

# The members only the retired envelope wrote, beside those above: the hosted run's own, read off the hosted plane's answer.
_RETIRED_HOSTED_MEMBERS: frozenset[str] = frozenset({"http_status", "retry_after_seconds", "run_status"})


# The parameters of ``client.argument_invalid``, which ``agent_argument_error`` takes.
_ARGUMENT_REFUSAL_PARAMS: frozenset[str] = frozenset({"argument", "reason"})


def _written_member(*, node: ast.AST) -> str | None:
    """The string a dictionary display or a subscript assignment writes as a key, ``None`` for any other node."""
    match node:
        case ast.Dict(keys=keys):
            for key in keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in _RETIRED_ENVELOPE_MEMBERS | _RETIRED_HOSTED_MEMBERS:
                    return key.value
            return None
        case ast.Assign(targets=targets):
            for target in targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    written = target.slice.value
                    if isinstance(written, str) and written in _RETIRED_ENVELOPE_MEMBERS | _RETIRED_HOSTED_MEMBERS:
                        return written
            return None
        case _:
            return None


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

    def test_no_agent_cli_module_writes_a_member_of_the_retired_envelope(self) -> None:
        """No agent CLI module builds a payload with a member of the envelope the problem replaced, a hosted run's included.

        A run on a runner used to leave in that envelope, built by hand as a dictionary; its failure is now the problem the
        runner or the client produced, so no key of that envelope is written anywhere in the agent CLI.
        """
        package_dir = Path(pipelex.cli.agent_cli.__file__).parent
        offenders: list[str] = []
        for source_file in sorted(package_dir.rglob("*.py")):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                member = _written_member(node=node)
                if member is not None:
                    offenders.append(f"{source_file.relative_to(package_dir)}:{getattr(node, 'lineno', 0)} writes '{member}'")
        assert not offenders, f"These lines write a member of the envelope the problem replaced: {offenders}"
