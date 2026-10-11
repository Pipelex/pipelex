from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.kernel import judgment_ops
from pipelex.kernel.prompt_assembly import AssembledUserPrompt
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import load_entry
from pipelex.test_extras.mthds_corpus.resources import entries_root


@pytest.mark.asyncio(loop_scope="class")
class TestBindingJudgeEvidence:
    async def test_v28_a_judge_reading_a_bound_total_sees_it_alone(self, mocker: MockerFixture) -> None:
        """The evidence is the judge's prompt rendered over its plain input names, so it shows the bound total and nothing else of the invoice."""
        entry = load_entry(directory=entries_root() / "feature_binding_step_judge_amount")
        assembly_spy = mocker.spy(judgment_ops, "assemble_user_prompt")
        inputs: dict[str, Any] = {
            "invoice": {"concept": "invoice_approval.Invoice", "content": {"supplier": "Chantier Naval Le Bihan", "total": 7420.0}},
        }

        await PipelexMTHDSProtocol(library_dirs=[str(entry.directory)], pipe_run_mode=PipeRunMode.DRY).execute(pipe_code="check_total", inputs=inputs)

        assert assembly_spy.call_count == 1
        evidence = assembly_spy.spy_return
        assert isinstance(evidence, AssembledUserPrompt)
        assert evidence.text == "The total of an invoice, in euros: 7420.0"
        assert "Chantier Naval Le Bihan" not in evidence.text
        assert not evidence.images
        assert not evidence.documents
