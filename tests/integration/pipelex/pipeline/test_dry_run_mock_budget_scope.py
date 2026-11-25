import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.pipes.declared_item_count_scope import scoped_dry_run_mock_budget
from pipelex.core.pipes.exceptions import DryRunMockBudgetError
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.pipe_run_mode import PipeRunMode

# A pipe taking ten texts and making ten more: a dry run with mock inputs builds ten mock inputs, then ten mock outputs.
_TEN_IN_TEN_OUT = """domain = "budget_scope"
description = "Ten texts in, ten texts out"
main_pipe = "rewrite_items"

[pipe.rewrite_items]
type = "PipeLLM"
description = "Rewrite the texts"
inputs = { items = "Text[10]" }
output = "Text[10]"
prompt = '''Rewrite these texts:

@items
'''
"""


def _batch_over_texts(*, branch: str) -> str:
    """A batch over `Text[20]` whose branch makes one output per item, the branch being `branch`'s own pipe."""
    branch_pipes = {
        "llm_text": """[pipe.handle_item]
type = "PipeLLM"
description = "Rewrite one text"
inputs = { item = "Text" }
output = "Text"
prompt = "Rewrite $item"
""",
        "compose_text": """[pipe.handle_item]
type = "PipeCompose"
description = "Wrap one text"
inputs = { item = "Text" }
output = "Text"
template = "Wrapped: $item"
""",
        "llm_structured": """[concept.Idea]
description = "An idea"

[concept.Idea.structure]
title = { type = "text", description = "The idea's title", required = true }

[pipe.handle_item]
type = "PipeLLM"
description = "Make one idea"
inputs = { item = "Text" }
output = "Idea"
prompt = "Make an idea from $item"
""",
    }
    return f"""domain = "budget_scope"
description = "A batch over twenty texts"
main_pipe = "handle_all"

{branch_pipes[branch]}
[pipe.handle_all]
type = "PipeBatch"
description = "Handle each text"
inputs = {{ items = "Text[20]" }}
output = "{"Idea" if branch == "llm_structured" else "Text"}[]"
branch_pipe_code = "handle_item"
input_list_name = "items"
input_item_name = "item"
"""


def _raised_from_budget(*, error: BaseException) -> bool:
    """Whether the budget's refusal is in `error`'s chain of causes."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, DryRunMockBudgetError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _mock_inputs_runner() -> PipelexMTHDSProtocol:
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, mock_inputs=True)
    return PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunMockBudgetScope:
    async def test_a_runs_mock_inputs_and_its_pipes_spend_one_budget(self, mocker: MockerFixture) -> None:
        """Ten mock inputs and ten mock outputs are twenty items of one run, past a budget of fifteen."""
        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 25)
        response = await _mock_inputs_runner().execute(pipe_code="rewrite_items", mthds_contents=[_TEN_IN_TEN_OUT])
        assert len(response.pipe_output.main_stuff.as_list_of_fixed_content_type(TextContent).items) == 10

        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 15)
        with pytest.raises(Exception) as exc_info:  # ruff: ignore[pytest-raises-too-broad] - the refusal may arrive wrapped by the run's failure
            await _mock_inputs_runner().execute(pipe_code="rewrite_items", mthds_contents=[_TEN_IN_TEN_OUT])
        assert _raised_from_budget(error=exc_info.value)

    @pytest.mark.parametrize("branch", ["llm_text", "compose_text"])
    async def test_every_mock_output_spends_the_budget(self, branch: str) -> None:
        """A branch making a text spends as much as one making a structured object: one mock item per output."""
        with scoped_dry_run_mock_budget() as structured_tally:
            await validate_bundles_in_process(mthds_contents=[_batch_over_texts(branch="llm_structured")])
        with scoped_dry_run_mock_budget() as text_tally:
            await validate_bundles_in_process(mthds_contents=[_batch_over_texts(branch=branch)])

        assert text_tally.built == structured_tally.built

    @pytest.mark.parametrize("branch", ["llm_text", "compose_text"])
    async def test_a_batch_of_text_outputs_exhausts_one_shared_budget(self, mocker: MockerFixture, branch: str) -> None:
        """The batch's twenty mock inputs and twenty mock text outputs, with its branch's own dry run, pass a budget of forty."""
        mthds = _batch_over_texts(branch=branch)
        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 40)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundles_in_process(mthds_contents=[mthds])

        problem = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert any(item.code == PipelexErrorCode.DEPLOYMENT_DRY_RUN_MOCK_BUDGET_EXCEEDED for item in problem.errors or [])
