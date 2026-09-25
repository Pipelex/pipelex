"""The bridge payload refuses malformed extras at the WIRE.

A `PipelexPipeRunInput` crosses a process boundary, so its extras are whatever
the other side put there. Declaring the field `dict[str, str]` says nothing
about its contents: a key with a newline in it, or a mapping with a thousand
entries, would decode happily and only surface much later, inside whichever
telemetry capture first tried to use it. Validating at construction makes that a
payload-decoding error naming the field — the same bargain `storage_scope`
already struck one field over.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.runtime_bridge.payloads import PipelexPipeRunInput
from pipelex.system.run_extras import RUN_EXTRAS_MAX_ENTRIES


def _payload(extras: dict[str, str]) -> PipelexPipeRunInput:
    return PipelexPipeRunInput(
        storage_scope="org_a/mt_b/run_c",
        user_id="test-user",
        pipe_code="some_pipe",
        extras=extras,
    )


class TestTheWireRefusesMalformedRunExtras:
    def test_the_field_defaults_to_an_empty_mapping(self) -> None:
        """A host with no extras to send sends none, and that is not an error.

        `user_id` and `storage_scope` are required here because a missing one
        used to be invented; a missing label invents nothing, so it defaults.
        """
        payload = PipelexPipeRunInput(storage_scope="org_a/mt_b/run_c", user_id="test-user", pipe_code="some_pipe")
        assert payload.extras == {}

    @pytest.mark.parametrize(
        "extras",
        [
            pytest.param({}, id="empty-mapping"),
            pytest.param({"organization": "org_acme"}, id="the-hosted-plane-shape"),
            pytest.param({"organization": "org_acme", "workspace": "ws-1"}, id="two-keys"),
        ],
    )
    def test_well_formed_extras_cross_the_wire(self, extras: dict[str, str]) -> None:
        assert _payload(extras).extras == extras

    @pytest.mark.parametrize(
        "bad_extras",
        [
            pytest.param({"Organization": "org_acme"}, id="uppercase-key"),
            pytest.param({"org-id": "org_acme"}, id="hyphen-in-key"),
            pytest.param({"": "org_acme"}, id="empty-key"),
            pytest.param({"organization": ""}, id="empty-value"),
            pytest.param({"organization": "org acme"}, id="space-in-value"),
            pytest.param({"organization": "org_acme\n"}, id="trailing-newline-in-value"),
            pytest.param({"organization": "v" * 129}, id="value-one-over-the-length-cap"),
            pytest.param({f"g{index}": "v" for index in range(RUN_EXTRAS_MAX_ENTRIES + 1)}, id="one-over-the-entry-cap"),
        ],
    )
    def test_malformed_extras_are_refused_at_construction(self, bad_extras: dict[str, str]) -> None:
        with pytest.raises(ValidationError):
            _payload(bad_extras)

    def test_the_extras_survive_a_json_round_trip(self) -> None:
        """The payload is decoded from JSON on the far side, so the field must round-trip."""
        original = _payload({"organization": "org_acme"})
        round_tripped = PipelexPipeRunInput.model_validate(original.model_dump(mode="json"))
        assert round_tripped == original
        assert round_tripped.extras == {"organization": "org_acme"}
