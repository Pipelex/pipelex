"""The reasons the runtime gives `request.unsupported` that a client tells one refusal apart by.

A reason rides the problem's `params.reason`, so a client branches on the code and the reason together, never on
the problem's text. This module imports nothing, so a client of the hosted API reads it without loading the
interpreter.
"""

#: A runner older than 0.89.0, whose `POST /v1/pipe-io` resolved a method sent as content strings, met a method calling
#: another one by its address, which that resolution could not fetch. No runtime of this release gives it: `/v1/pipe-io`
#: now resolves the method's tree and answers a call into a package nothing shipped with its invalid verdict. A hosted
#: run still tells this refusal apart by it, since the run route fetches such a dependency and a hosted API may run an
#: older runner.
ADDRESS_DEPENDENCY_UNSUPPORTED_REASON = "address_based_dependency"

#: A table input, such as a CSV file, given by a URL that is not a local file path: this runtime reads a table from a
#: local file alone, so the form the input uses is one it does not accept, whatever the URL names.
REMOTE_TABLE_UNSUPPORTED_REASON = "remote_table_url"
