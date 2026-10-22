"""The reasons the runtime gives `request.unsupported` that a client tells one refusal apart by.

A reason rides the problem's `params.reason`, so a client branches on the code and the reason together, never on
the problem's text. This module imports nothing, so a client of the hosted API reads it without loading the
interpreter.
"""

#: A table input, such as a CSV file, given by a URL that is not a local file path: this runtime reads a table from a
#: local file alone, so the form the input uses is one it does not accept, whatever the URL names.
REMOTE_TABLE_UNSUPPORTED_REASON = "remote_table_url"

#: A method given as the MTHDS protocol's `files` map, a tree path to file entry, to the local runtime or the runner,
#: which take a method as its bundles' contents (`mthds_contents`) or as their library directories' method trees.
METHOD_FILES_UNSUPPORTED_REASON = "method_files_on_local_runtime"
