from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.bundle_elaborator import BundleElaborator
from pipelex.core.interpreter.exceptions import BundleElaboratorError, PipelexInterpreterError
from pipelex.core.interpreter.validation_error_categorizer import PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD, categorize_blueprint_validation_error
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_content, load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData


class PipelexInterpreter(BaseModel):
    """MTHDS -> PipelexBundleBlueprint"""

    @classmethod
    def make_pipelex_bundle_blueprint(cls, bundle_path: Path | None = None, *, mthds_content: str | None = None) -> PipelexBundleBlueprint:
        blueprint_dict: dict[str, Any]
        try:
            if bundle_path is not None:
                blueprint_dict = load_toml_from_path(path=str(bundle_path))
                blueprint_dict[PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD] = str(bundle_path)
            elif mthds_content is not None:
                blueprint_dict = load_toml_from_content(content=mthds_content)
            else:
                msg = "Either 'bundle_path' or 'mthds_content' must be provided for the PipelexInterpreter to make a PipelexBundleBlueprint"
                raise PipelexInterpreterError(msg)
        except TomlError as exc:
            msg = f"TOML syntax error at line {exc.lineno}, column {exc.colno}: {exc.message}"
            raise PipelexInterpreterError(msg) from exc

        if not blueprint_dict:
            msg = "Could not make 'PipelexBundleBlueprint': no blueprint found in the MTHDS file"
            raise PipelexInterpreterError(msg)

        try:
            pipelex_bundle_blueprint = PipelexBundleBlueprint.model_validate(blueprint_dict)
            pipelex_bundle_blueprint.source = str(bundle_path) if bundle_path else None
        except ValidationError as exc:
            # TODO: Move this to the validate_bundle function
            blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] = []

            for error in exc.errors():
                categorized_error = categorize_blueprint_validation_error(blueprint_dict=blueprint_dict, error=error)
                if categorized_error:
                    blueprint_validation_errors.append(categorized_error)

            raise PipelexInterpreterError(
                message=format_pydantic_validation_error(exc),
                validation_errors=blueprint_validation_errors,
            ) from exc

        try:
            return BundleElaborator.elaborate(bundle=pipelex_bundle_blueprint)
        except BundleElaboratorError as exc:
            raise PipelexInterpreterError(message=str(exc)) from exc
