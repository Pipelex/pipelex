from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipelexInterpreterError, PLXDecodeError
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_content, load_toml_from_path


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
            with open(file_path, encoding="utf-8") as f:
                # Read first 100 characters (should be enough to find domain)
                content = f.read(100)
                # Remove leading whitespace and check if it starts with "domain ="
                stripped_content = content.lstrip()
                return stripped_content.startswith("domain =")
        except Exception:
            # If we can't read the file, it's not a valid Pipelex file
            return False

    @classmethod
    def make_pipelex_bundle_blueprint(cls, bundle_path: str | None = None, plx_content: str | None = None) -> PipelexBundleBlueprint:
        if bundle_path is None and plx_content is None:
            msg = "Either 'bundle_path' or 'plx_content' must be provided for the PipelexInterpreter to make a PipelexBundleBlueprint"
            raise PipelexInterpreterError(msg)
        blueprint_dict: dict[str, Any] | None = None
        try:
            if bundle_path is not None:
                blueprint_dict = load_toml_from_path(path=bundle_path)
                blueprint_dict.update(source=bundle_path)
            elif plx_content is not None:
                blueprint_dict = load_toml_from_content(content=plx_content)
        except TomlError as exc:
            raise PLXDecodeError(message=exc.message, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno) from exc

        if not blueprint_dict:
            msg = "Could not make 'PipelexBundleBlueprint': no blueprint found in the PLX file"
            raise PipelexInterpreterError(msg)

        try:
            return PipelexBundleBlueprint.model_validate(blueprint_dict)
        except ValidationError as exc:
            # Parse Pydantic validation errors into structured error data
            validation_errors: list[PipelexBundleBlueprintValidationErrorData] = []

            for error in exc.errors():
                loc = error.get("loc", ())
                msg = error.get("msg", "Unknown validation error")

                # Determine if it's a pipe or concept error
                pipe_code: str | None = None
                concept_code: str | None = None
                other: str | None = None

                if len(loc) >= 2:
                    if loc[0] == "pipe":
                        pipe_code = str(loc[1])
                    elif loc[0] == "concept":
                        concept_code = str(loc[1])
                    else:
                        other = str(loc[0])
                elif len(loc) == 1:
                    other = str(loc[0])

                # Create field path string
                field_path = " → ".join(str(item) for item in loc)

                # Create validation error data
                val_error = PipelexBundleBlueprintValidationErrorData(
                    pipe_code=pipe_code,
                    concept_code=concept_code,
                    field_path=field_path,
                    message=msg,
                    other=other,
                    domain=blueprint_dict.get("domain"),
                    source=blueprint_dict.get("source") or bundle_path,
                )
                validation_errors.append(val_error)

            raise PipelexInterpreterError(
                message=str(exc),
                validation_errors=validation_errors,
            ) from exc
