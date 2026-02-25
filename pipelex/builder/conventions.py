"""Conventions for builder output file names.

These constants define the standard file names produced by the builder
and expected by the runner when auto-detecting from a directory.
"""

from pipelex.core.interpreter.helpers import MTHDS_EXTENSION

DEFAULT_BUNDLE_FILE_NAME = f"bundle{MTHDS_EXTENSION}"
DEFAULT_INPUTS_FILE_NAME = "inputs.json"
