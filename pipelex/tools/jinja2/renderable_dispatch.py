"""Decide from a value's type whether a filter may call the rendering method a protocol names.

The `with_images`, `format` and `tag` filters call a method on the value they are handed, and the template
sandbox never sees that call. A runtime-checkable Protocol cannot license it on its own: on Python 3.11,
`isinstance` against one is a `hasattr` test, which a template satisfies with
`namespace(render_with_images=...)`, and the filter would then call whatever callable the template put
there. So a filter also requires the value's class to define every member of the protocol, looked up with
`inspect.getattr_static` on the type: a template can build instances, but never a class.
"""

import inspect

from typing_extensions import get_protocol_members

_ABSENT = object()


def type_implements(*, value: object, protocol: type) -> bool:
    """Whether the class of `value` defines every member of `protocol`, read from the type and never from the instance."""
    value_type = type(value)
    return all(inspect.getattr_static(value_type, member, _ABSENT) is not _ABSENT for member in get_protocol_members(protocol))
