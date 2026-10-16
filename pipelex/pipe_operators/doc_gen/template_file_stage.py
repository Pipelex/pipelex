"""The interpreter's part in a `PipeDocGen` print from a template file, installed on the runtime hub at boot.

The print stage, a kernel-layer leaf, reads the template file through the method file store and hands this stage what
needs the method itself (`pipelex.cogt.doc_gen.template_file_stage`):

- an HTML template file is rendered with the step's data as the compose stage of a `PipeCompose` renders an HTML
  template, with the whole stack, its filters included: the step's working memory is typed again by the concepts of the
  run's library crate, in the run's own library when this process holds it, such as in a local run, and in a library
  loaded from the crate for the render otherwise, such as in an activity on a worker;
- the findings of the engine's check of an office template file, at a dry print, fail the step when one is an error,
  and join the validation verdict's warnings otherwise, or the log when no validation collects them.
"""

import uuid
from collections.abc import Generator
from contextlib import contextmanager

from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile
from pipelex.cogt.doc_gen.template_check import TemplateFinding
from pipelex.cogt.doc_gen.template_file_stage import TemplateFileStageProtocol
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.interpreter_hub import get_current_library_id_or_none, get_library_manager, scoped_current_library
from pipelex.kernel.compose_ops import build_compose_context
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.doc_gen.doc_gen_rendering import render_doc_gen_template
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenRunError, PipeDocGenTemplateCheckError
from pipelex.pipe_run.dry_run_warning_collector import report_dry_run_warning
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.validation_error_types import TemplateCheckErrorType

_RENDER_LIBRARY_PREFIX = "doc_gen_template_render"


@contextmanager
def _library_for_crate(*, crate: LibraryCrate) -> Generator[None, None, None]:
    """Make current a library holding the crate: the current one when it already does, or one loaded for the block.

    The current library already holds the crate in the process that loaded the run's method, so its concepts' classes
    are the ones the step's data was built with. Anywhere else, such as in an activity on a worker, a library is loaded
    from the crate, which reads no file, and torn down after the block.
    """
    library_manager = get_library_manager()
    current_library_id = get_current_library_id_or_none()
    if current_library_id is not None and library_manager.is_crate_loaded(library_id=current_library_id, fingerprint=crate.fingerprint):
        yield
        return
    library_id, _ = library_manager.open_library(library_id=f"{_RENDER_LIBRARY_PREFIX}_{uuid.uuid4().hex}")
    try:
        with scoped_current_library(library_id=library_id):
            # The crate was validated where the run's method was loaded.
            library_manager.load_from_crate(library_id=library_id, crate=crate, is_crate_prevalidated=True)
            yield
    finally:
        library_manager.teardown(library_id=library_id)


def _step_codes(*, template_file: ComposedTemplateFile) -> tuple[str | None, str]:
    """The domain and the code of the step naming the template file."""
    parsed = QualifiedRef.parse_pipe_ref(raw=template_file.pipe_ref)
    return parsed.domain_path, parsed.local_code


class DocGenTemplateFileStage(TemplateFileStageProtocol):
    """Renders an HTML template file with its step's data, and reports the findings of an office template's check."""

    @override
    async def render_html_template_file(self, *, template_file: ComposedTemplateFile, template_source: str) -> str:
        _domain_code, pipe_code = _step_codes(template_file=template_file)
        render_context = template_file.render_context
        if render_context is None:
            msg = f"PipeDocGen '{pipe_code}' names the template file '{template_file.name}' with nothing to render it with."
            raise PipeDocGenRunError(msg)
        crate = LibraryCrate.model_validate(render_context.crate)
        with _library_for_crate(crate=crate):
            working_memory = hydrate_working_memory(render_context.working_memory_raw)
            context = build_compose_context(memory=working_memory, runtime_params=render_context.runtime_params)
            return await render_doc_gen_template(
                pipe_code=pipe_code,
                template=template_source,
                category=TemplateCategory.HTML,
                context=context,
                label=f"template file '{template_file.name}'",
                templating_style=resolve_templating_style(authored=None),
            )

    @override
    def report_template_findings(self, *, template_file: ComposedTemplateFile, findings: list[TemplateFinding]) -> None:
        domain_code, pipe_code = _step_codes(template_file=template_file)
        for finding in findings:
            if not finding.severity.is_error:
                _report_template_warning(domain_code=domain_code, pipe_code=pipe_code, template_file=template_file.name, finding=finding)
        errors = [finding for finding in findings if finding.severity.is_error]
        if errors:
            listed = "\n".join(f"- {finding.message}" + (f" ({finding.location})" if finding.location else "") for finding in errors)
            msg = f"PipeDocGen '{pipe_code}': the template file '{template_file.name}' does not fit the step's inputs:\n{listed}"
            raise PipeDocGenTemplateCheckError(msg)


def _report_template_warning(*, domain_code: str | None, pipe_code: str, template_file: str, finding: TemplateFinding) -> None:
    """Report a warning of the template check as an advisory item, located at its step, its file and the place in it.

    An engine that answers an empty location names no place, so the item's `template_location` is left unset.
    """
    location = finding.location or None
    location_suffix = f" ({location})" if location is not None else ""
    warning = ValidationErrorItem(
        category=ValidationErrorCategory.DRY_RUN,
        error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
        pipe_code=pipe_code,
        domain_code=domain_code,
        template_file=template_file,
        template_location=location,
        message=f"PipeDocGen '{pipe_code}', template file '{template_file}': {finding.message}{location_suffix}",
    )
    if report_dry_run_warning(warning=warning):
        return
    finding_fields: dict[str, str] = {"pipe_code": pipe_code, "template_file": template_file, "finding_message": finding.message}
    if location is not None:
        finding_fields["finding_location"] = location
    log.warning("The template check of a PipeDocGen found a warning in its template file", fields=finding_fields)
