class ActionsAllowlistGuardError(Exception):
    """The Actions allowlist guard cannot run as configured: a missing or malformed allowlist, an unreadable workflow, or nothing to scan.

    A plain ``Exception`` rather than a ``PipelexError``: it never leaves the ``pipelex-dev check-actions-allowlist``
    command, which reports it as a failed check, so it carries no ``error_type`` on any wire and has no page in the
    error reference.
    """
