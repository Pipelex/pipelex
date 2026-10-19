"""Guard + regression for the message-setting ``__init__`` of ``PipelexError`` subclasses.

A subclass that mixes in ``ValueError`` / ``TypeError`` (so Pydantic validators wrap
its raises into a ``ValidationError``) must list the ``PipelexError``-derived base
*first*. Otherwise ``BaseException.__init__`` — inherited through ``ValueError`` /
``TypeError`` — shadows ``PipelexError.__init__`` in the MRO, ``self.message`` is never
set, and ``to_problem()`` raises ``AttributeError`` the moment a problem-building path touches
the instance.
"""

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import RoutingProfileBlueprintValueError
from pipelex.errors.error_class_discovery import iter_pipelex_error_subclasses
from pipelex.errors.problem import ProblemView
from pipelex.pipe_operators.compose.exceptions import ConstructFieldBlueprintValueError


class TestPipelexErrorMessageInit:
    def test_no_subclass_shadows_message_setting_init(self) -> None:
        """No loaded ``PipelexError`` subclass lets ``ValueError`` / ``TypeError`` precede
        ``PipelexError`` in its MRO — that ordering shadows the ``.message`` setter.
        """
        offenders: list[str] = []
        for error_cls in iter_pipelex_error_subclasses():
            mro = error_cls.__mro__
            pipelex_index = mro.index(PipelexError)
            for shadow_cls in (ValueError, TypeError):
                if shadow_cls in mro and mro.index(shadow_cls) < pipelex_index:
                    offenders.append(f"{error_cls.__module__}.{error_cls.__name__} (lists {shadow_cls.__name__} before PipelexError)")
        assert not offenders, "Exception classes shadow PipelexError.__init__ — `.message` will be unset:\n" + "\n".join(offenders)

    @pytest.mark.builds_problems_without_required_params(reason="builds the error with a message alone, to check how its message is set")
    @pytest.mark.parametrize("error_cls", [ConstructFieldBlueprintValueError, RoutingProfileBlueprintValueError])
    def test_message_set_and_problem_succeeds(self, error_cls: type[PipelexError]) -> None:
        """A reordered ``(PipelexError, ValueError)`` mixin sets ``.message``, keeps its
        ``ValueError`` identity (so Pydantic still wraps validator raises), and builds a problem.
        """
        message = "the configuration section is invalid"
        exc = error_cls(message)
        assert exc.message == message
        assert isinstance(exc, ValueError)
        problem = exc.to_problem(view=ProblemView.OPERATOR)
        assert problem.diagnostics is not None
        assert problem.diagnostics.message == message
        assert problem.diagnostics.error_class == error_cls.__name__
