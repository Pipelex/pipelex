from pathlib import Path
from typing import Any

from typing_extensions import override

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenFactoryError
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint, template_required_roots
from pipelex.pipe_operators.doc_gen.template_file_resource import bundle_resource_of_template_file
from pipelex.tools.jinja2.template_category import TemplateCategory


def bundle_dir_of_source(source: str | None) -> Path | None:
    """The directory of the bundle file a pipe was loaded from, or None for a bundle loaded from a string.

    The library manager sets a pipe blueprint's `source` to the bundle file this host read the bundle from just before
    the pipe is built, and clears it otherwise (`LibraryCrate.host_bundle_files`), so the label a caller sends with
    content strings, or a `source` the bundle's own text writes, never reaches here: a content-string load has no
    directory, and nothing beside it is read from this host's disk.
    """
    if source is None or "://" in source:
        return None
    source_path = Path(source)
    if not source_path.is_file():
        return None
    return source_path.resolve().parent


class PipeDocGenFactory(PipeFactoryProtocol[PipeDocGenBlueprint, PipeDocGen]):
    @classmethod
    @override
    def make(
        cls,
        *,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeDocGenBlueprint,
    ) -> PipeDocGen:
        document_concept = get_native_concept(native_concept=NativeConceptCode.DOCUMENT)
        if not get_concept_library().is_compatible(tested_concept=output.concept, wanted_concept=document_concept, strict=True):
            msg = (
                f"The output of PipeDocGen '{pipe_code}' is '{output.concept.concept_ref}', which is not a Document. "
                f"Declare the output as {document_concept.concept_ref}, or as a concept that refines it."
            )
            raise PipeDocGenFactoryError(msg)

        template = blueprint.template
        template_path: str | None = None
        if blueprint.template_file is not None:
            bundle_dir = bundle_dir_of_source(blueprint.source)
            if bundle_dir is None:
                # A bundle loaded from content strings reads only the files submitted with it, never this host's disk. An
                # office template is read from them when the step prints, so the pipe keeps only its name, and the run
                # carries the file in its crate.
                resource = bundle_resource_of_template_file(template_file=blueprint.template_file)
                if resource is None:
                    msg = (
                        f"PipeDocGen '{pipe_code}' names the template file '{blueprint.template_file}', which was not supplied with its "
                        "bundle. A bundle loaded from content strings has no directory to find the file in, so the file must be "
                        f"submitted with it, keyed by the same path, '{blueprint.template_file}'. A bundle loaded from a directory "
                        "finds it beside its file."
                    )
                    raise PipeDocGenFactoryError(msg)
                if blueprint.format.is_template_html:
                    try:
                        template = resource.inline_bytes().decode("utf-8")
                    except UnicodeError as exc:
                        msg = f"PipeDocGen '{pipe_code}' could not read the template file '{blueprint.template_file}' as UTF-8 text."
                        raise PipeDocGenFactoryError(msg) from exc
                    cls._check_html_template_file(pipe_code=pipe_code, template=template, inputs=inputs, template_file=blueprint.template_file)
            else:
                # A bundle this host read from a file finds its template file beside it, and never among submitted files.
                resolved_path = cls._resolve_template_file(pipe_code=pipe_code, template_file=blueprint.template_file, bundle_dir=bundle_dir)
                if blueprint.format.is_template_html:
                    try:
                        template = resolved_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError) as exc:
                        msg = f"PipeDocGen '{pipe_code}' could not read the template file '{blueprint.template_file}' as UTF-8 text."
                        raise PipeDocGenFactoryError(msg) from exc
                    cls._check_html_template_file(pipe_code=pipe_code, template=template, inputs=inputs, template_file=blueprint.template_file)
                else:
                    template_path = str(resolved_path)

        return PipeDocGen(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            doc_gen_format=blueprint.format,
            doc_gen_choice=blueprint.model,
            template=template,
            template_file=blueprint.template_file,
            template_path=template_path,
            filename=blueprint.filename,
        )

    @classmethod
    def _resolve_template_file(cls, *, pipe_code: str, template_file: str, bundle_dir: Path) -> Path:
        """The template file's path, beside the bundle and inside its directory, checked to exist.

        The messages name the template file as the method does and never the host's path to it: the bundle a
        refusal is located in already says which one, and a dependency's install path is not the caller's to read.
        """
        resolved_path = (bundle_dir / template_file).resolve()
        if not resolved_path.is_relative_to(bundle_dir):
            msg = f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which is outside its bundle's directory."
            raise PipeDocGenFactoryError(msg)
        if not resolved_path.is_file():
            msg = f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which does not exist beside its bundle."
            raise PipeDocGenFactoryError(msg)
        return resolved_path

    @classmethod
    def _check_html_template_file(cls, *, pipe_code: str, template: str, inputs: InputStuffSpecs, template_file: str) -> None:
        """Check an HTML template file at load, as an inline template is checked when its blueprint validates."""
        declared_inputs = set(inputs.variables)
        try:
            roots = template_required_roots(
                template_source=template,
                template_category=TemplateCategory.HTML,
                declared_inputs=declared_inputs,
                label=f"template file '{template_file}'",
            )
        except ValueError as exc:
            msg = f"PipeDocGen '{pipe_code}': {exc}"
            raise PipeDocGenFactoryError(msg) from exc
        for root in sorted(roots - declared_inputs):
            msg = f"Variable '{root}' in the template file '{template_file}' of PipeDocGen '{pipe_code}' is not in the inputs of the pipe."
            raise PipeDocGenFactoryError(msg)
