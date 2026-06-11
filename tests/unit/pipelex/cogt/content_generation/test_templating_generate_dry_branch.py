"""Unit tests for the ``run_mode == DRY`` branch in the templating leaf (templating_generate).

Contract: under DRY the template is never rendered (a marker string is returned instead), but a
syntactically broken jinja2 template must STILL fail loudly — dry-run validation relies on the
parse check surviving the mock.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import TemplatingAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.templating_generate import templating_gen_text
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError


class TestTemplatingGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode, template: str) -> TemplatingAssignment:
        return TemplatingAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_templating_dry"),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
            context={"the_answer": "42"},
            template=template,
            category=TemplateCategory.BASIC,
        )

    @pytest.mark.asyncio
    async def test_dry_returns_marker_without_rendering(self, mocker: MockerFixture) -> None:
        """DRY: marker string returned; render_template is never invoked."""
        render_spy = mocker.patch("pipelex.cogt.content_generation.templating_generate.render_template")

        result = await templating_gen_text(self._assignment(run_mode=PipeRunMode.DRY, template="{{ the_answer }}"))

        render_spy.assert_not_called()
        assert result.startswith("DRY RUN:")

    @pytest.mark.asyncio
    async def test_dry_still_raises_on_broken_template(self) -> None:
        """DRY preserves the jinja2 parse check: a broken template fails loudly instead of being mocked over."""
        with pytest.raises(Jinja2TemplateSyntaxError):
            await templating_gen_text(self._assignment(run_mode=PipeRunMode.DRY, template="{% if unclosed %}"))

    @pytest.mark.asyncio
    async def test_live_renders_template(self) -> None:
        """LIVE renders for real."""
        result = await templating_gen_text(self._assignment(run_mode=PipeRunMode.LIVE, template="answer={{ the_answer }}"))

        assert result == "answer=42"
