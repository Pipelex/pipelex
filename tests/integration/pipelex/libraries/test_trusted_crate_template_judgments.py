from collections import Counter
from typing import TYPE_CHECKING, Any

import jinja2
import pytest
from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import clear_current_library, get_library_manager, set_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_machinery import template_guard_lint
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM

if TYPE_CHECKING:
    from collections.abc import Callable

DESCRIBE_PROMPT = "Describe the photo $photo of the report $report.title, whose body reads: $report.body"
RENDER_TEMPLATE = "<h1>{{ report.title }}</h1>{% if note %}<p>{{ note }}</p>{% endif %}<div>{{ report.body }}</div>"
UNGUARDED_RENDER_TEMPLATE = "<h1>{{ report.title }}</h1><p>{{ note }}</p><div>{{ report.body }}</div>"


def _mthds(*, render_template: str) -> str:
    return f"""\
domain = "trusted_templates"
description = "A crate whose templates a trusted load does not judge again"
main_pipe = "main"

[concept.Report]
description = "A report"

[concept.Report.structure]
title = {{ type = "text", description = "The title", required = true }}
body = {{ type = "text", description = "The body", required = true }}

[pipe.describe]
type = "PipeLLM"
description = "Describe the report's photo"
inputs = {{ report = "Report", photo = "Image" }}
output = "Text"
model = "$testing-text"
prompt = "{DESCRIBE_PROMPT}"

[pipe.render]
type = "PipeCompose"
description = "Render the report"
inputs = {{ report = "Report", note = "Text?" }}
output = "Html"

[pipe.render.template]
category = "html"
template = "{render_template}"

[pipe.main]
type = "PipeSequence"
description = "Describe, then render"
inputs = {{ report = "Report", photo = "Image", note = "Text?" }}
output = "Html"
steps = [
    {{ pipe = "describe", result = "description" }},
    {{ pipe = "render", result = "page" }},
]
"""


def _make_crate(*, render_template: str) -> LibraryCrate:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_mthds(render_template=render_template), mthds_source="trusted.mthds")
    return LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])


def _open_workflow_library(*, library_id: str) -> None:
    """Open a library the way the Temporal workflow does: fresh, with its own seeded class registry, and current."""
    library = get_library_manager().open_fresh_library(library_id=library_id)
    scoped_registry = ClassRegistry()
    scoped_registry.register_classes_dict(KajsonManager.get_class_registry().get_classes_dict())
    library.set_class_registry(scoped_registry)
    set_current_library(library_id=library_id)


def _counting_parses(*, mocker: MockerFixture) -> Counter[str]:
    """Count every Jinja2 parse by the source parsed, from now on."""
    parsed_sources: Counter[str] = Counter()
    original_parse: Callable[..., Any] = jinja2.Environment.parse

    def counting_parse(self: jinja2.Environment, source: str, *args: Any, **kwargs: Any) -> Any:
        parsed_sources[source] += 1
        return original_parse(self, source, *args, **kwargs)

    mocker.patch.object(jinja2.Environment, "parse", counting_parse)
    return parsed_sources


class TestTrustedCrateTemplateJudgments:
    @pytest.mark.parametrize("is_crate_prevalidated", [True, False])
    def test_a_load_parses_each_template_once_and_judges_it_unless_trusted(self, mocker: MockerFixture, is_crate_prevalidated: bool) -> None:
        """A trusted load runs no template lint, an untrusted one runs them; both parse each template at most once and build the same pipes."""
        crate = _make_crate(render_template=RENDER_TEMPLATE)
        private_name_spy = mocker.spy(template_guard_lint, "detect_private_name_references")
        optional_guard_spy = mocker.spy(template_guard_lint, "detect_unguarded_optional_references")
        parsed_sources = _counting_parses(mocker=mocker)
        library_manager = get_library_manager()
        library_id = f"trusted-templates-{is_crate_prevalidated}"
        try:
            _open_workflow_library(library_id=library_id)
            library_manager.load_from_crate(library_id=library_id, crate=crate, is_crate_prevalidated=is_crate_prevalidated)
            pipe_library = library_manager.get_library(library_id=library_id).pipe_library
            describe_pipe = pipe_library.get_required_pipe(pipe_code="trusted_templates.describe")
            render_pipe = pipe_library.get_required_pipe(pipe_code="trusted_templates.render")
        finally:
            clear_current_library()
            library_manager.teardown(library_id=library_id)

        if is_crate_prevalidated:
            assert private_name_spy.call_count == 0
            assert optional_guard_spy.call_count == 0
        else:
            # Both templates get the private-name lint; only the template of the pipe with an optional input gets the guard-lint.
            assert private_name_spy.call_count == 2
            assert optional_guard_spy.call_count == 1
        repeated_parses = {source: count for source, count in parsed_sources.items() if count > 1}
        assert not repeated_parses, f"templates parsed more than once in one load: {repeated_parses}"

        # What a run reads is built either way: the photo the prompt presents, and the authored template.
        assert isinstance(describe_pipe, PipeLLM)
        image_references = describe_pipe.llm_prompt_spec.user_image_references or []
        assert [image_reference.variable_path for image_reference in image_references] == ["photo"]
        assert isinstance(render_pipe, PipeCompose)
        assert render_pipe.template is not None
        assert render_pipe.template.strip() == RENDER_TEMPLATE

    def test_only_an_untrusted_load_refuses_an_unguarded_optional(self) -> None:
        """The guard-lint refuses a template its untrusted load reads an optional input in unguarded; a trusted load takes it."""
        crate = _make_crate(render_template=UNGUARDED_RENDER_TEMPLATE)
        library_manager = get_library_manager()
        opened_library_ids: list[str] = []
        try:
            untrusted_library_id = "unguarded-untrusted"
            _open_workflow_library(library_id=untrusted_library_id)
            opened_library_ids.append(untrusted_library_id)
            # The pipe's model validator raises the lint's refusal, which pydantic reports as its own validation error.
            with pytest.raises(ValidationError, match="uses the optional input 'note' unguarded"):
                library_manager.load_from_crate(library_id=untrusted_library_id, crate=crate)

            trusted_library_id = "unguarded-trusted"
            _open_workflow_library(library_id=trusted_library_id)
            opened_library_ids.append(trusted_library_id)
            trusted_pipes = library_manager.load_from_crate(library_id=trusted_library_id, crate=crate, is_crate_prevalidated=True)
            assert "trusted_templates.render" in {pipe.pipe_ref for pipe in trusted_pipes}
        finally:
            clear_current_library()
            for library_id in opened_library_ids:
                library_manager.teardown(library_id=library_id)
