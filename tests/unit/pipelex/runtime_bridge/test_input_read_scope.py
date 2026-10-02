"""`read_scope` on the runtime bridge's run payload: required, path-safe, and above the storage scope, at the wire."""

import pytest
from pydantic import ValidationError

from pipelex.runtime_bridge.payloads import PipelexPipeRunInput


class TestBridgePayloadReadScope:
    def test_omitting_it_is_an_error_at_the_wire(self) -> None:
        with pytest.raises(ValidationError, match="read_scope"):
            PipelexPipeRunInput.model_validate({"pipe_code": "p", "user_id": "u1", "storage_scope": "org_abc/run_1"})

    def test_a_storage_scope_outside_the_read_scope_is_refused_at_the_wire(self) -> None:
        with pytest.raises(ValidationError, match="does not lie under its read_scope"):
            PipelexPipeRunInput(pipe_code="p", user_id="u1", storage_scope="org_other/run_1", read_scope="org_abc")

    def test_an_unsafe_read_scope_is_refused_at_the_wire(self) -> None:
        with pytest.raises(ValidationError, match="Invalid read_scope"):
            PipelexPipeRunInput(pipe_code="p", user_id="u1", storage_scope="org_abc/run_1", read_scope="../org_abc")
