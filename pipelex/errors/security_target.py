"""What a security refusal refused, named without naming it: the vocabulary the security event carries.

A security event (:mod:`pipelex.errors.security_event`) says what kind of thing a security rule refused, and, for a
destination, which class of destination it was, and never the thing itself: the URL, the path, the template or the
schema is the caller's content or the method's. The kind follows from the refusal's code alone; the class is known
only where the refusal is decided, so a raise site states it on the error with
:meth:`~pipelex.base_exceptions.PipelexError.with_security_target_class`.

This module imports nothing from Pipelex, so the base error class can name the class without a cycle.
"""

from enum import StrEnum


class SecurityTargetKind(StrEnum):
    """The kind of thing a security rule refused, which the refusal's code decides."""

    URL = "url"
    PATH = "path"
    TEMPLATE = "template"
    SCHEMA = "schema"
    DEPENDENCY = "dependency"
    OBJECT_KEY = "object_key"
    RESULT_LOCATION = "result_location"


class SecurityTargetClass(StrEnum):
    """The class of destination a refused URL or storage key points at, as the raise site classifies it.

    The first five are the values the error registry gives the ``target_class`` parameter of the URL refusals:
    a loopback address, a private address (any other address that is not publicly routable), a link-local
    address, a cloud metadata endpoint, and a scheme the runtime does not read, a ``file://`` URL or a bare
    path on the server's disk among them. ``foreign_storage_key`` is a storage key outside the run's read scope,
    which another tenant's run wrote; the registry has no value for it yet.
    """

    LOOPBACK = "loopback"
    PRIVATE = "private"
    LINK_LOCAL = "link_local"
    METADATA = "metadata"
    SCHEME = "scheme"
    FOREIGN_STORAGE_KEY = "foreign_storage_key"
