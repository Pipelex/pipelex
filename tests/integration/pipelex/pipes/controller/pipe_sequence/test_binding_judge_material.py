from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.kernel import judgment_ops
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import load_entry
from pipelex.test_extras.mthds_corpus.resources import entries_root


@pytest.mark.asyncio(loop_scope="class")
class TestBindingJudgeMaterial:
    async def test_v28_a_judge_reading_a_bound_total_sees_it_alone(self, mocker: MockerFixture) -> None:
        """The judgment's material is keyed by the judge's plain input names, so it holds the bound total and nothing else of the invoice."""
        entry = load_entry(directory=entries_root() / "feature_binding_step_judge_amount")
        material_spy = mocker.spy(judgment_ops, "build_judgment_material")
        inputs: dict[str, Any] = {
            "invoice": {"concept": "invoice_approval.Invoice", "content": {"supplier": "Chantier Naval Le Bihan", "total": 7420.0}},
        }

        await PipelexMTHDSProtocol(library_dirs=[str(entry.directory)], pipe_run_mode=PipeRunMode.DRY).execute(pipe_code="check_total", inputs=inputs)

        assert material_spy.call_count == 1
        state, images, documents = material_spy.spy_return
        assert state == {"total_amount": 7420.0}
        assert images == {}
        assert documents == {}
