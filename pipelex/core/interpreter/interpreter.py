from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.exceptions import PipelexInterpreterError, PLXDecodeError
from pipelex.core.interpreter.validation_error_categorizer import categorize_blueprint_validation_error
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_content, load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData


class PipelexInterpreter(BaseModel):
    """plx -> PipelexBundleBlueprint"""

    # TODO: rethink this method
    @staticmethod
    def is_pipelex_file(file_path: Path) -> bool:
        """Check if a file is a valid Pipelex PLX file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if the file is a Pipelex file, False otherwise

        Criteria:
            - Has .plx extension
            - Starts with "domain =" (ignoring leading whitespace)

        """
        # Check if it has .toml extension
        if file_path.suffix != ".plx":
            return False

        # Check if file exists
        if not file_path.exists() or not file_path.is_file():
            return False

        try:
            # Read the first few lines to check for "domain ="
            with open(file_path, encoding="utf-8") as file:
                # Read first 100 characters (should be enough to find domain)
                content = file.read(100)
                # Remove leading whitespace and check if it starts with "domain ="
                stripped_content = content.lstrip()
                return stripped_content.startswith("domain =")
        except Exception:
            # If we can't read the file, it's not a valid Pipelex file
            return False

    @classmethod
    def make_pipelex_bundle_blueprint(cls, bundle_path: str | None = None, plx_content: str | None = None) -> PipelexBundleBlueprint:
        blueprint_dict: dict[str, Any]
        try:
            if bundle_path is not None:
                blueprint_dict = load_toml_from_path(path=bundle_path)
                blueprint_dict.update(source=bundle_path)
            elif plx_content is not None:
                blueprint_dict = load_toml_from_content(content=plx_content)
            else:
                msg = "Either 'bundle_path' or 'plx_content' must be provided for the PipelexInterpreter to make a PipelexBundleBlueprint"
                raise PipelexInterpreterError(msg)
        except TomlError as exc:
            raise PLXDecodeError(message=exc.message, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno) from exc

        if not blueprint_dict:
            msg = "Could not make 'PipelexBundleBlueprint': no blueprint found in the PLX file"
            raise PipelexInterpreterError(msg)

        try:
            return PipelexBundleBlueprint.model_validate(blueprint_dict)
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
