"""The interpreter's part in a `PipeDocGen` print from a template file, installed on the runtime hub at boot.

The print stage, a kernel-layer leaf, reads the template file through the method file store and hands this stage what
needs the method itself (`pipelex.cogt.doc_gen.template_file_stage`):

- an HTML template file is rendered with the step's data as the compose stage of a `PipeCompose` renders an HTML
  template, with the whole stack, its filters included: the stuffs the step's inputs name are typed again by the
  concepts of the run's library crate, in the run's own library when this process holds it, such as in a local run, and
  otherwise, such as in an activity on a worker, in a library loaded from those concepts alone, which this process keeps
  for the prints that follow (`RenderLibraryCache`);
- the findings of the engine's check of an office template file, at a dry print, fail the step when one is an error,
  and join the validation verdict's warnings otherwise, or the log when no validation collects them.
"""

import threading
import uuid
from collections import OrderedDict
from collections.abc import Generator
from contextlib import contextmanager
from typing import NamedTuple

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, TemplateRenderContext
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
# How many libraries typing the data of HTML template files this process keeps once no print uses them: one per set of
# concepts, so a worker printing for a handful of methods loads each one's concepts once, and one printing for many
# keeps the ones it used last. A library a print is using is never torn down, however many there are.
_RENDER_LIBRARY_CAPACITY = 8


class _RenderLibrary(NamedTuple):
    library_id: str
    users: int


class RenderLibraryCache:
    """The libraries this process loaded from the concepts of a run's crate to type the data of HTML template files, by fingerprint.

    Loading a crate builds its concepts' classes, which costs more than the render, so a library is kept after its print
    for the next print typing data with the same concepts, such as the next document of the same method. Libraries no
    print is using are torn down beyond the capacity, the least recently used first. A library torn down by someone else,
    such as by the library manager's teardown of every library, is loaded again.
    """

    def __init__(self, *, capacity: int) -> None:
        self._capacity = capacity
        self._lock = threading.Lock()
        self._libraries: OrderedDict[str, _RenderLibrary] = OrderedDict()

    @contextmanager
    def library_for(self, *, concepts_crate: LibraryCrate) -> Generator[str, None, None]:
        """A library holding the crate's concepts, held for the block, the one kept for its fingerprint or one loaded for it."""
        library_id = self._acquire(concepts_crate=concepts_crate)
        try:
            yield library_id
        finally:
            self._release(fingerprint=concepts_crate.fingerprint)

    def held_library_ids(self) -> list[str]:
        """The libraries kept, in use or not, the least recently used first."""
        with self._lock:
            return [render_library.library_id for render_library in self._libraries.values()]

    def release_idle(self) -> None:
        """Tear down every library kept that no print is using."""
        with self._lock:
            idle = [fingerprint for fingerprint, render_library in self._libraries.items() if render_library.users <= 0]
            to_tear_down = [self._libraries.pop(fingerprint).library_id for fingerprint in idle]
        for library_id in to_tear_down:
            get_library_manager().teardown(library_id=library_id)

    def _acquire(self, *, concepts_crate: LibraryCrate) -> str:
        library_manager = get_library_manager()
        fingerprint = concepts_crate.fingerprint
        with self._lock:
            kept = self._libraries.get(fingerprint)
            if kept is not None and library_manager.is_crate_loaded(library_id=kept.library_id, fingerprint=fingerprint):
                self._libraries[fingerprint] = kept._replace(users=kept.users + 1)
                self._libraries.move_to_end(fingerprint)
                return kept.library_id
            library_id, _ = library_manager.open_library(library_id=f"{_RENDER_LIBRARY_PREFIX}_{uuid.uuid4().hex}")
            try:
                # The crate's concepts were validated where the run's method was loaded.
                library_manager.load_from_crate(library_id=library_id, crate=concepts_crate, is_crate_prevalidated=True)
            except BaseException:
                library_manager.teardown(library_id=library_id)
                raise
            # A library kept under this fingerprint and torn down by someone else is replaced.
            self._libraries[fingerprint] = _RenderLibrary(library_id=library_id, users=1)
            self._libraries.move_to_end(fingerprint)
            return library_id

    def _release(self, *, fingerprint: str) -> None:
        to_tear_down: list[str] = []
        with self._lock:
            kept = self._libraries.get(fingerprint)
            if kept is not None:
                self._libraries[fingerprint] = kept._replace(users=kept.users - 1)
            idle = [kept_fingerprint for kept_fingerprint, render_library in self._libraries.items() if render_library.users <= 0]
            for kept_fingerprint in idle[: max(0, len(idle) - self._capacity)]:
                to_tear_down.append(self._libraries.pop(kept_fingerprint).library_id)
        for library_id in to_tear_down:
            get_library_manager().teardown(library_id=library_id)


#: The libraries this process keeps to type the data of HTML template files.
RENDER_LIBRARIES = RenderLibraryCache(capacity=_RENDER_LIBRARY_CAPACITY)


@contextmanager
def _library_typing(*, render_context: TemplateRenderContext) -> Generator[None, None, None]:
    """Make current a library whose concepts type the step's data: the run's own when current, or one holding its concepts.

    The current library is the run's own in the process that loaded the run's method, so its concepts' classes are the
    ones the step's data was built with. Anywhere else, such as in an activity on a worker, the data is typed in a library
    loaded from the run's concepts alone, which reads no file, and which this process keeps for the prints that follow.
    """
    library_manager = get_library_manager()
    current_library_id = get_current_library_id_or_none()
    if current_library_id is not None and library_manager.is_crate_loaded(
        library_id=current_library_id, fingerprint=render_context.crate_fingerprint
    ):
        yield
        return
    concepts_crate = LibraryCrate.model_validate(render_context.concepts_crate)
    with RENDER_LIBRARIES.library_for(concepts_crate=concepts_crate) as library_id, scoped_current_library(library_id=library_id):
        yield


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
        with _library_typing(render_context=render_context):
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
