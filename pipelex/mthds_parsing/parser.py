from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.method_trees.file_references import BundleFileOrigin, BundleValidationContext
from pipelex.mthds_parsing.bundle_elaborator import BundleElaborator
from pipelex.mthds_parsing.exceptions import BundleElaboratorError, MthdsParserError
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.mthds_parsing.validation_error_categorizer import PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD, categorize_blueprint_validation_error
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_content, load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class MthdsParser(BaseModel):
    """MTHDS -> PipelexBundleBlueprint"""

    @classmethod
    def make_pipelex_bundle_blueprint(
        cls,
        bundle_path: Path | None = None,
        *,
        mthds_content: str | None = None,
        mthds_source: str | None = None,
        file_origin: BundleFileOrigin = BundleFileOrigin.METHOD_TREE,
    ) -> PipelexBundleBlueprint:
        """Parse one MTHDS source into a ``PipelexBundleBlueprint``.

        Exactly one of ``bundle_path`` (load from disk) or ``mthds_content``
        (load from a string) must be provided. ``mthds_source`` is an optional
        logical source for the *in-memory* path: the API submits sourceless bundle
        text (``mthds_contents: list[str]``), so without it ``blueprint.source``
        is ``None`` and cross-file diagnostics misfire. It is seeded into the
        blueprint dict before validation (as the ``source`` field), so it lands
        both on the validated blueprint AND on any blueprint-validation error the
        categorizer reads off that dict — mirroring the real file path the disk
        path already records, and overriding any ``source`` the bundle text
        itself declared. With ``bundle_path``, it names the file in place of its path on
        this host, as a host names a file of a tree it wrote out for a caller by its tree path.

        ``file_origin`` says where the bundle's steps find the files they name, and so the rule a file
        reference, such as a ``PipeDocGen`` step's ``template_file``, is held to when the blueprint validates.
        A caller loading ``mthds_content`` that no loader will place in a method tree passes ``SUBMITTED_FILES``:
        such a bundle reads only the files submitted with it, so a step naming a file none of them could be keyed
        by, such as one through a ``..`` segment, is refused here, as a blueprint item at the step, whatever the
        request sends. ``METHOD_TREE``, the default, checks a reference's form alone, for the load to resolve it
        in the bundle's tree; it is the only origin of a bundle read from ``bundle_path``, so it is ignored there.
        """
        blueprint_dict: dict[str, Any]
        validation_context: BundleValidationContext
        try:
            if bundle_path is not None:
                blueprint_dict = load_toml_from_path(path=str(bundle_path))
                blueprint_dict[PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD] = mthds_source if mthds_source is not None else str(bundle_path)
                validation_context = BundleValidationContext(file_origin=BundleFileOrigin.METHOD_TREE)
            elif mthds_content is not None:
                validation_context = BundleValidationContext(file_origin=file_origin)
                blueprint_dict = load_toml_from_content(content=mthds_content)
                # Seed the logical source unconditionally (``None`` when unnamed): this
                # overrides any ``source`` the bundle text declared and keeps the success
                # path (``model_validate`` below) and the error path (the categorizer,
                # which reads ``source`` off this dict) in agreement on one value.
                blueprint_dict[PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD] = mthds_source
            else:
                msg = "Either 'bundle_path' or 'mthds_content' must be provided for the MthdsParser to make a PipelexBundleBlueprint"
                raise MthdsParserError(msg)
        except TomlError as exc:
            toml_message = exc.message
            if bundle_path is not None and mthds_source is not None:
                # The file is named by its source, never by its path on this host, the error's message included.
                toml_message = toml_message.replace(str(bundle_path), mthds_source)
            msg = f"TOML syntax error at line {exc.lineno}, column {exc.colno}: {toml_message}"
            source = str(bundle_path) if bundle_path is not None and mthds_source is None else mthds_source
            raise MthdsParserError(
                msg,
                validation_errors=[
                    PipelexBundleBlueprintValidationErrorData(
                        source=source,
                        message=msg,
                        # tomli counts both from 1, as the item's locators do.
                        line=exc.lineno,
                        column=exc.colno,
                    )
                ],
            ) from exc

        if not blueprint_dict:
            msg = "Could not make 'PipelexBundleBlueprint': no blueprint found in the MTHDS file"
            raise MthdsParserError(msg)

        try:
            # ``source`` is already populated from the seeded ``blueprint_dict`` above
            # (disk path → real file path; in-memory path → ``mthds_source``), so no
            # post-validate re-assignment is needed.
            pipelex_bundle_blueprint = PipelexBundleBlueprint.model_validate(blueprint_dict, context=validation_context)
        except ValidationError as exc:
            # TODO: Move this to the validate_bundle function
            # Every error becomes an item, categorized or not, so none hides another; only a concept's
            # union-branch noise is left out, its table branch reporting the same fault.
            blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] = []

            for error in exc.errors():
                categorized_error = categorize_blueprint_validation_error(blueprint_dict=blueprint_dict, error=error)
                if categorized_error:
                    blueprint_validation_errors.append(categorized_error)

            raise MthdsParserError(
                message=format_pydantic_validation_error(exc),
                validation_errors=blueprint_validation_errors,
            ) from exc

        try:
            elaborated_blueprint = BundleElaborator.elaborate(bundle=pipelex_bundle_blueprint)
        except BundleElaboratorError as exc:
            raise MthdsParserError(message=str(exc)) from exc
        # Only a bundle read from a file here may read beside it: a content string's `mthds_source` is a label.
        if bundle_path is not None:
            elaborated_blueprint.mark_read_from_host_file(bundle_file=Path(bundle_path))
        return elaborated_blueprint
