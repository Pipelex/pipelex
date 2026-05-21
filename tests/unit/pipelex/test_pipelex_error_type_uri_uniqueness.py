"""Class-name uniqueness guard for the ``PipelexError.type_uri()`` keyspace.

Every loaded ``PipelexError`` subclass must produce a unique ``type_uri``. A
collision would mean two distinct error classes point at the same documentation
page — catches future class-name reuses at CI time, not at docs-build time.
"""

import pipelex.cogt.exceptions  # noqa: F401
import pipelex.core.concepts.exceptions  # noqa: F401
import pipelex.core.concepts.native.exceptions  # noqa: F401
import pipelex.core.concepts.structure_generation.exceptions  # noqa: F401
import pipelex.core.domains.exceptions  # noqa: F401
import pipelex.core.interpreter.exceptions  # noqa: F401
import pipelex.core.memory.exceptions  # noqa: F401
import pipelex.core.pipes.exceptions  # noqa: F401
import pipelex.core.pipes.inputs.exceptions  # noqa: F401
import pipelex.core.pipes.stuff_spec.exceptions  # noqa: F401
import pipelex.core.stuffs.exceptions  # noqa: F401
import pipelex.libraries.exceptions  # noqa: F401
import pipelex.pipe_operators.compose.exceptions  # noqa: F401
import pipelex.pipe_operators.exceptions  # noqa: F401
import pipelex.pipe_operators.extract.exceptions  # noqa: F401
import pipelex.pipe_operators.img_gen.exceptions  # noqa: F401
import pipelex.pipe_operators.llm.exceptions  # noqa: F401
import pipelex.pipe_operators.search.exceptions  # noqa: F401
import pipelex.pipe_operators.shared.template_image_analyzer  # noqa: F401
import pipelex.pipeline.exceptions  # noqa: F401
import pipelex.system.environment  # noqa: F401
import pipelex.system.exceptions  # noqa: F401
import pipelex.temporal.exceptions  # noqa: F401
import pipelex.tools.misc.toml_utils  # noqa: F401
import pipelex.tools.secrets.secrets_errors  # noqa: F401
import pipelex.tools.secrets.secrets_utils  # noqa: F401
import pipelex.tools.storage.exceptions  # noqa: F401
from pipelex.base_exceptions import PipelexError


class TestPipelexErrorTypeUriUniqueness:
    def test_all_pipelex_error_subclasses_have_unique_type_uris(self) -> None:
        """Every ``PipelexError`` subclass produces a unique ``type_uri``."""
        seen: dict[str, str] = {}
        stack: list[type[PipelexError]] = [PipelexError]
        while stack:
            cls = stack.pop()
            uri = cls.type_uri()
            if uri in seen and seen[uri] != cls.__name__:
                msg = f"type_uri collision: {cls.__name__} and {seen[uri]} both produce {uri!r}"
                raise AssertionError(msg)
            seen[uri] = cls.__name__
            stack.extend(cls.__subclasses__())
