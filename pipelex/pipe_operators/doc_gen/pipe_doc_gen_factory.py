from collections.abc import Callable
from pathlib import Path
from typing import Any

from mthds.method_tree.exceptions import MethodTreeRefusedError
from typing_extensions import override

from pipelex.core.bundle_resources.bundle_resource import BundleResource
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.method_trees.building_bundle import get_building_tree_bundle
from pipelex.core.method_trees.file_references import reference_refusal_reason, resolve_bundle_file_reference
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenFactoryError
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint, template_required_roots
from pipelex.pipe_operators.doc_gen.template_file_resource import bundle_resource_of_template_file
from pipelex.tools.jinja2.template_category import TemplateCategory


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
            tree_bundle = get_building_tree_bundle()
            read_template_bytes: Callable[[], bytes]
            if tree_bundle is None:
                # A bundle loaded from content strings reads only the files submitted with it, never this host's disk. An
                # office template is read from them when the step prints, so the pipe keeps only its name, and the run
                # carries the file in its crate.
                read_template_bytes = cls._submitted_template_file(pipe_code=pipe_code, template_file=blueprint.template_file).inline_bytes
            else:
                # A bundle this host read from its disk finds its template file in its method tree, and never among
                # submitted files.
                resolved_path = cls._resolve_template_file(pipe_code=pipe_code, template_file=blueprint.template_file, tree_bundle=tree_bundle)
                read_template_bytes = resolved_path.read_bytes
                if not blueprint.format.is_template_html:
                    template_path = str(resolved_path)
            if blueprint.format.is_template_html:
                # An HTML template is read and checked now, from disk as from the submitted bytes, as written.
                template = cls._html_template_file_text(pipe_code=pipe_code, template_file=blueprint.template_file, read_bytes=read_template_bytes)
                cls._check_html_template_file(pipe_code=pipe_code, template=template, inputs=inputs, template_file=blueprint.template_file)

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
    def _resolve_template_file(cls, *, pipe_code: str, template_file: str, tree_bundle: TreeBundle) -> Path:
        """Where the template file lies on this host, resolved in the bundle's method tree.

        The file is the tree's file the reference names, resolved against the bundle's tree path, `..` included as long
        as it stays in the tree, by a lookup in the tree's set of tree paths: a file the membership rule keeps out of the
        tree, or any file outside it, is refused, and its path is never opened. The messages name the template file as
        the method does and files by their tree paths, never the host's path to them: the bundle a refusal is located in
        already says which one, and a dependency's install path is not the caller's to read.
        """
        try:
            resolved_tree_path = resolve_bundle_file_reference(reference=template_file, tree_bundle=tree_bundle)
        except MethodTreeRefusedError as exc:
            reason = reference_refusal_reason(refusal_error=exc, tree_bundle=tree_bundle)
            msg = f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which its method tree cannot give it. {reason}"
            raise PipeDocGenFactoryError(msg) from exc
        return tree_bundle.tree.file_location(resolved_tree_path)

    @classmethod
    def _submitted_template_file(cls, *, pipe_code: str, template_file: str) -> BundleResource:
        """The template file submitted with a bundle loaded from content strings, which the current library holds."""
        resource = bundle_resource_of_template_file(template_file=template_file)
        if resource is None:
            msg = (
                f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which was not supplied with its "
                "bundle. A bundle loaded from content strings has no directory to find the file in, so the file must be "
                f"submitted with it, keyed by the same path, '{template_file}'. A bundle loaded from a folder "
                "finds it in its method tree."
            )
            raise PipeDocGenFactoryError(msg)
        return resource

    @classmethod
    def _html_template_file_text(cls, *, pipe_code: str, template_file: str, read_bytes: Callable[[], bytes]) -> str:
        """An HTML template file's text, decoded from its bytes as written, line endings included."""
        try:
            return read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as exc:
            msg = f"PipeDocGen '{pipe_code}' could not read the template file '{template_file}' as UTF-8 text."
            raise PipeDocGenFactoryError(msg) from exc

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
