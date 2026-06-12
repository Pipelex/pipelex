"""Pin the D13 primary-blueprint selection rule: first blueprint declaring ``main_pipe``, else first.

``select_primary_blueprint`` is the single selection rule shared by every validate surface — the
canonical report's ``bundle_blueprint``, the graph arm's target derivation, and the Temporal
activity. The qualified ``main_pipe_ref`` (``domain.main_pipe``) must come from the SAME blueprint
that was selected, and be ``None`` when nothing in the batch declares a ``main_pipe``.

Pure parsing test (no Pipelex boot, no library): blueprints come straight from the interpreter.
"""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.pipeline.validate_bundle import select_primary_blueprint

_NO_MAIN_PIPE_MTHDS = """
domain = "alpha"
description = "Concepts only, no main_pipe"

[concept.Thing]
description = "A thing"
"""

_MAIN_PIPE_BETA_MTHDS = """
domain = "beta"
description = "Declares a main_pipe"
main_pipe = "do_it"

[pipe.do_it]
type = "PipeLLM"
description = "Do it"
inputs = { doc = "Text" }
output = "Text"
prompt = "Do it with $doc"
"""

_MAIN_PIPE_GAMMA_MTHDS = """
domain = "gamma"
description = "Also declares a main_pipe"
main_pipe = "do_other"

[pipe.do_other]
type = "PipeLLM"
description = "Do something else"
inputs = { doc = "Text" }
output = "Text"
prompt = "Do something else with $doc"
"""


def _blueprint(mthds_content: str) -> PipelexBundleBlueprint:
    return PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)


class TestSelectPrimaryBlueprint:
    def test_none_declaring_selects_first_with_no_ref(self) -> None:
        """No blueprint declares main_pipe: the first is primary and the ref is None."""
        blueprints = [_blueprint(_NO_MAIN_PIPE_MTHDS), _blueprint(_NO_MAIN_PIPE_MTHDS.replace("alpha", "alpha_two"))]

        selection = select_primary_blueprint(blueprints)

        assert selection.blueprint is blueprints[0]
        assert selection.main_pipe_ref is None

    def test_first_declaring_wins_over_earlier_non_declaring(self) -> None:
        """The first blueprint declaring main_pipe is primary, even when it is not first in the batch."""
        blueprints = [_blueprint(_NO_MAIN_PIPE_MTHDS), _blueprint(_MAIN_PIPE_BETA_MTHDS)]

        selection = select_primary_blueprint(blueprints)

        assert selection.blueprint is blueprints[1]
        assert selection.main_pipe_ref == "beta.do_it"

    def test_multiple_declaring_first_wins(self) -> None:
        """When several blueprints declare main_pipe, the first declaring one wins."""
        blueprints = [_blueprint(_MAIN_PIPE_BETA_MTHDS), _blueprint(_MAIN_PIPE_GAMMA_MTHDS)]

        selection = select_primary_blueprint(blueprints)

        assert selection.blueprint is blueprints[0]
        assert selection.main_pipe_ref == "beta.do_it"
