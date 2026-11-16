"""The interpreter's part in a `PipeDocGen` print from a template file, installed on the runtime hub at boot.

The print stage, a kernel-layer leaf, reads the template file through the method file store and hands this stage what
needs the method itself (`pipelex.cogt.doc_gen.template_file_stage`):

- an HTML template file is rendered with the step's data as the compose stage of a `PipeCompose` renders an HTML
  template, with the whole stack, its filters included: the stuffs the step's inputs name are typed again by the
  concepts of the run's library crate, in the run's own library when this process holds it, such as in a local run, and
  otherwise, such as in an activity on a worker, in a library loaded from those concepts alone, which this process keeps
  for the prints that follow (`pipelex.libraries.concepts_libraries`);
- the findings of the engine's check of an office template file, at a dry print, or at a live one for a template a
  run input supplies, fail the step when one is an error, and join the validation verdict's warnings otherwise, or the
  log when no validation collects them. An error in a template a run input supplies is the caller's
  (`PipeDocGenTemplateInputUnfitError`), and one in the method's own template file the method's.
"""

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile
from pipelex.cogt.doc_gen.template_check import TemplateFinding
from pipelex.cogt.doc_gen.template_file_stage import TemplateFileStageProtocol
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.kernel.compose_ops import build_compose_context
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.libraries.concepts_libraries import typed_by_run_concepts
from pipelex.pipe_operators.doc_gen.doc_gen_rendering import render_doc_gen_template
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenRunError, PipeDocGenTemplateCheckError, PipeDocGenTemplateInputUnfitError
from pipelex.pipe_run.dry_run_warning_collector import report_dry_run_warning
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.validation_error_types import TemplateCheckErrorType


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
            raise PipeDocGenRunError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
        with typed_by_run_concepts(crate_fingerprint=render_context.crate_fingerprint, concepts_crate=render_context.concepts_crate):
            working_memory = hydrate_working_memory(render_context.working_memory_raw)
            context = build_compose_context(memory=working_memory, runtime_params=render_context.runtime_params)
            return await render_doc_gen_template(
                pipe_code=pipe_code,
                template=template_source,
                category=TemplateCategory.HTML,
                context=context,
                label=f"template file '{template_file.name}'",
                template_field="template_file",
                templating_style=resolve_templating_style(authored=None),
            )

    @override
    def report_template_findings(self, *, template_file: ComposedTemplateFile, findings: list[TemplateFinding]) -> None:
        domain_code, pipe_code = _step_codes(template_file=template_file)
        for finding in findings:
            if not finding.severity.is_error:
                _report_template_warning(domain_code=domain_code, pipe_code=pipe_code, template_file=template_file, finding=finding)
        errors = [finding for finding in findings if finding.severity.is_error]
        if not errors:
            return
        listed = "\n".join(f"- {finding.message}" + (f" ({finding.location})" if finding.location else "") for finding in errors)
        findings_text = "; ".join(finding.message for finding in errors)
        input_file = template_file.input_file
        if input_file is not None:
            # The file is the caller's, so the refusal is the caller's to act on, naming the input and never its file.
            msg = f"PipeDocGen '{pipe_code}': {template_file.desc} does not fit the step's inputs:\n{listed}"
            raise PipeDocGenTemplateInputUnfitError(msg, input_name=input_file.input_name, finding=findings_text)
        msg = f"PipeDocGen '{pipe_code}': the template file '{template_file.name}' does not fit the step's inputs:\n{listed}"
        raise PipeDocGenTemplateCheckError(msg).with_params(template=template_file.name, reason="does_not_fit", finding=findings_text)


def _report_template_warning(*, domain_code: str | None, pipe_code: str, template_file: ComposedTemplateFile, finding: TemplateFinding) -> None:
    """Report a warning of the template check as an advisory item, located at its step, its file and the place in it.

    An engine that answers an empty location names no place, so the item's `template_location` is left unset. A template
    a run input supplies is named by the input, `the input 'workbook'`, as its job names it.
    """
    location = finding.location or None
    location_suffix = f" ({location})" if location is not None else ""
    template_label = template_file.desc if template_file.input_file is not None else f"template file '{template_file.name}'"
    warning = ValidationErrorItem(
        category=ValidationErrorCategory.DRY_RUN,
        error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
        pipe_code=pipe_code,
        domain_code=domain_code,
        template_file=template_file.name,
        template_location=location,
        message=f"PipeDocGen '{pipe_code}', {template_label}: {finding.message}{location_suffix}",
    )
    if report_dry_run_warning(warning=warning):
        return
    finding_fields: dict[str, str] = {"pipe_code": pipe_code, "template_file": template_file.name, "finding_message": finding.message}
    if location is not None:
        finding_fields["finding_location"] = location
    log.warning("The template check of a PipeDocGen found a warning in its template file", fields=finding_fields)
