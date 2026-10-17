import ast
from pathlib import Path
from typing import Any, cast

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.models import NextStep, ProblemItem, ProblemLocation, SuggestedFix
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import ApiResponseError, RunFailedError
from pipelex_sdk.runs import RunStatus
from pydantic import BaseModel

import pipelex.cli.agent_cli
from pipelex.cli.agent_cli.commands.agent_output import problem_payload
from pipelex.cli.agent_cli.commands.run._run_hosted import hosted_failure_problem
from pipelex.errors.problem import PipelexProblem
from tests.unit.pipelex.cli.agent_cli.test_data import HostedPlaneRefusals, OperatorViewAnswers, StoredRunReports, UndeclaredMembers

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


# The parts of a reported problem, each read against the model that declares its members. A problem's `params` and a
# fix's `ops` are the code's and the operation's own, so they are not walked.
_PROBLEM_PARTS: dict[type[BaseModel], dict[str, type[BaseModel]]] = {
    PipelexProblem: {"next_step": NextStep, "location": ProblemLocation, "errors": ProblemItem, "run_error": PipelexProblem},
    ProblemItem: {"location": ProblemLocation, "suggested_fix": SuggestedFix},
}

# The command's own sentence, which rides beside the problem's members.
_COMMAND_MEMBERS: frozenset[str] = frozenset({"message"})


def _undeclared_members(*, document: dict[str, Any], shape: type[BaseModel], path: str) -> list[str]:
    """The members of ``document`` and of the parts it nests that their model does not declare, by their path."""
    allowed: set[str] = set(shape.model_fields)
    if path == "problem":
        allowed |= _COMMAND_MEMBERS
    offenders = [f"{path}.{name}" for name in document if name not in allowed]
    for name, part_shape in _PROBLEM_PARTS.get(shape, {}).items():
        part = document.get(name)
        if isinstance(part, dict):
            offenders += _undeclared_members(document=cast("dict[str, Any]", part), shape=part_shape, path=f"{path}.{name}")
        elif isinstance(part, list):
            for index_item, item in enumerate(cast("list[Any]", part)):
                if isinstance(item, dict):
                    offenders += _undeclared_members(document=cast("dict[str, Any]", item), shape=part_shape, path=f"{path}.{name}[{index_item}]")
    return offenders


def _refusal(*, status: int, body: str) -> ApiResponseError:
    """A refusal of the run request as the client raises it, the answer read the way the client reads it."""
    return ApiResponseError(
        f"API POST /v1/start failed ({status})",
        api_url="https://hosted.test",
        status=status,
        status_text="Refused",
        response_body=body,
        headers={},
        may_start_run=True,
    )


def _reported_failures() -> list[PipelineRequestError]:
    """Failures of a run on a runner whose answers carry members no reader declares, at every level."""
    return [
        _refusal(status=422, body=UndeclaredMembers.SENT),
        _refusal(status=401, body=HostedPlaneRefusals.UNAUTHORIZED),
        _refusal(status=429, body=HostedPlaneRefusals.RATE_LIMITED_BODY_DELAY),
        _refusal(status=409, body=OperatorViewAnswers.UNREADABLE_REQUEST_ID),
        RunFailedError(
            "Run finished with status FAILED",
            run_id="run_9",
            status=RunStatus.FAILED,
            error=RunErrorReport.model_validate(StoredRunReports.PROBLEM_WITH_REPORT_MEMBERS),
        ),
    ]


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

    def test_no_reported_problem_carries_a_member_its_reader_does_not_declare(self) -> None:
        """The document a run on a runner reports holds only the members the standard and Pipelex declare, at every level.

        A runner's answer may carry members beside its problem, those the envelope this CLI wrote before it reported
        problems used to read (`error_type`, `error_domain`, `retryable`) among them, and a reader that copied them
        through would bring that envelope back. This guards the emitted document itself, whatever builds it.
        """
        offenders: list[str] = []
        for failure in _reported_failures():
            document = problem_payload(problem=hosted_failure_problem(error=failure, credential_sent=True), message=None, extras={})
            offenders += [
                f"{type(failure).__name__}: {member}" for member in _undeclared_members(document=document, shape=PipelexProblem, path="problem")
            ]
        assert not offenders, f"These reported members are declared by no reader of the problem: {offenders}"
