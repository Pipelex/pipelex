from mthds.protocol.problem.registry import CoreCode

from pipelex.system.exceptions import ToolError


class TemplateSigilSyntaxError(ToolError):
    """Raised when a template contains a Pipelex sigil shape that violates the strict
    line-bounded `@` rule.

    The error message includes the 1-based line number, the offending sigil span, and a
    migration hint pointing the author at `$var` (inline) or `@@` (literal `@`). The sigil is misplaced in the
    method's own template, so it is the method's syntax error.
    """

    error_code = CoreCode.METHOD_SYNTAX
