from typing import Any

from mthds.method_tree.exceptions import MethodTreeRefusedError
from typing_extensions import override

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.method_trees.building_bundle import get_building_tree_bundle
from pipelex.core.method_trees.file_references import reference_refusal_reason, resolve_bundle_file_reference, resolve_crate_file_reference
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.core.method_trees.tree_bundle import MethodFileRef, TreeBundle, TreeBundleRef
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenFactoryError
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint, template_required_roots
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

        template_file_ref: MethodFileRef | None = None
        template_bundle_ref: TreeBundleRef | None = None
        template_file_text: str | None = None
        if blueprint.template is not None:
            template_bundle_ref = cls._inline_template_bundle_ref()
        if blueprint.template_file is not None:
            template_file = blueprint.template_file
            match get_building_tree_bundle():
                case TreeBundle() as tree_bundle:
                    # A bundle this process holds finds its template file in its method tree: read from this host's disk
                    # as a member of the tree, or parsed from a content string at the root of the tree of the files
                    # submitted with it.
                    resolved_tree_path = cls._resolve_template_file(pipe_code=pipe_code, template_file=template_file, tree_bundle=tree_bundle)
                    template_file_ref = MethodFileRef(tree_digest=tree_bundle.digest, tree_path=resolved_tree_path)
                    if blueprint.format.is_template_html:
                        # An HTML template file is read and checked now, as written, for the method's load; the print
                        # stage reads it again, where the step prints.
                        template_file_text = cls._html_template_file_text(
                            pipe_code=pipe_code,
                            template_file=template_file,
                            data=cls._read_tree_file(tree_bundle=tree_bundle, tree_path=resolved_tree_path),
                        )
                        cls._check_html_template_file(pipe_code=pipe_code, template=template_file_text, inputs=inputs, template_file=template_file)
                case TreeBundleRef() as tree_bundle_ref:
                    # A step built from a crate reads nothing: the crate names its tree by digest, and the host that
                    # assembled it resolved the reference in the tree and checked the file. The print stage reads it.
                    try:
                        resolved_tree_path = resolve_crate_file_reference(reference=template_file, tree_bundle_ref=tree_bundle_ref)
                    except MethodTreeRefusedError as exc:
                        msg = (
                            f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which its method tree cannot give it. {exc.message}"
                        )
                        raise PipeDocGenFactoryError(msg) from exc
                    template_file_ref = MethodFileRef(tree_digest=tree_bundle_ref.tree_digest, tree_path=resolved_tree_path)
                case None:
                    raise PipeDocGenFactoryError(cls._unsubmitted_template_file_message(pipe_code=pipe_code, template_file=template_file))

        pipe_doc_gen = PipeDocGen(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            doc_gen_format=blueprint.format,
            doc_gen_choice=blueprint.model,
            template=blueprint.template,
            template_file=blueprint.template_file,
            template_file_ref=template_file_ref,
            template_bundle_ref=template_bundle_ref,
            filename=blueprint.filename,
        )
        if template_file_text is not None:
            pipe_doc_gen.hold_template_file_text(template_file_text=template_file_text)
        return pipe_doc_gen

    @classmethod
    def _inline_template_bundle_ref(cls) -> TreeBundleRef | None:
        """The bundle of an inline template, as its method tree names it: what the template's relative URLs resolve against.

        Nothing is resolved here: a relative URL is the rendered HTML's, which only the print stage's engine reads, so each
        is resolved in the tree when the engine asks for its file. None for bundles parsed from content strings with no
        file submitted beside them, which belong to no tree, so their template's relative URLs name no file.
        """
        match get_building_tree_bundle():
            case TreeBundle() as tree_bundle:
                return tree_bundle.make_ref()
            case TreeBundleRef() as tree_bundle_ref:
                return tree_bundle_ref
            case None:
                return None

    @classmethod
    def _resolve_template_file(cls, *, pipe_code: str, template_file: str, tree_bundle: TreeBundle) -> str:
        """The tree path of the template file, resolved in the bundle's method tree.

        The file is the tree's file the reference names, resolved against the bundle's tree path, `..` included as long
        as it stays in the tree, by a lookup in the tree's set of tree paths: a file the membership rule keeps out of the
        tree, or any file outside it, is refused, and its path is never opened. Bundles parsed from content strings
        resolve it from the root of the tree of the files submitted with them. The messages name the template file as
        the method does and files by their tree paths, never the host's path to them: the bundle a refusal is located
        in already says which one, and a dependency's install path is not the caller's to read.
        """
        try:
            return resolve_bundle_file_reference(reference=template_file, tree_bundle=tree_bundle)
        except MethodTreeRefusedError as exc:
            if tree_bundle.tree_path is None:
                msg = cls._unsubmitted_template_file_message(pipe_code=pipe_code, template_file=template_file)
                raise PipeDocGenFactoryError(msg) from exc
            reason = reference_refusal_reason(refusal_error=exc, tree_bundle=tree_bundle)
            msg = f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which its method tree cannot give it. {reason}"
            raise PipeDocGenFactoryError(msg) from exc

    @staticmethod
    def _unsubmitted_template_file_message(*, pipe_code: str, template_file: str) -> str:
        return (
            f"PipeDocGen '{pipe_code}' names the template file '{template_file}', which was not supplied with its "
            "bundle. A bundle loaded from content strings has no directory to find the file in, so the file must be "
            f"submitted with it, keyed by the same path, '{template_file}'. A bundle loaded from a folder "
            "finds it in its method tree."
        )

    @classmethod
    def _read_tree_file(cls, *, tree_bundle: TreeBundle, tree_path: str) -> bytes | None:
        """The bytes of a file of the bundle's tree, as a library of this process holds the tree, checked against its hash.

        A tree a step is built in is always held: the library holds every tree it loads before it builds a pipe of one.
        None when the file's bytes are no longer the ones the tree's listing recorded, such as a file edited, removed or
        swapped for a link since: nothing is read from the disk past the hash check.
        """
        return LOCAL_METHOD_FILES.read_held_file(tree_digest=tree_bundle.tree.digest, tree_path=tree_path)

    @classmethod
    def _html_template_file_text(cls, *, pipe_code: str, template_file: str, data: bytes | None) -> str:
        """An HTML template file's text, decoded from its bytes as written, line endings included."""
        if data is None:
            msg = (
                f"PipeDocGen '{pipe_code}' could not read the template file '{template_file}' as its method tree listed it: "
                "the file changed or went missing since the tree was listed."
            )
            raise PipeDocGenFactoryError(msg)
        try:
            return data.decode("utf-8")
        except UnicodeError as exc:
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
