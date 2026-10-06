"""The default file names of a method directory: its bundle and its inputs.

`pipelex run` and `pipelex-agent run` look for these names when given a directory, and
`pipelex build inputs` and `pipelex codegen inputs` write the inputs file under them.
"""

from pipelex.mthds_parsing.helpers import MTHDS_EXTENSION

DEFAULT_BUNDLE_FILE_NAME = f"bundle{MTHDS_EXTENSION}"
DEFAULT_INPUTS_FILE_NAME = "inputs.json"
DEFAULT_INPUTS_TOML_FILE_NAME = "inputs.toml"
