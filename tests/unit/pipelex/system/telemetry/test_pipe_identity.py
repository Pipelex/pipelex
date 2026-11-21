import hashlib

import pytest
from pytest_mock import MockerFixture

from pipelex.system.job_metadata import RunMetadata
from pipelex.system.telemetry.otel_constants import PipelexSpanAttr
from pipelex.system.telemetry.pipe_identity import (
    PIPE_ID_HEX_LENGTH,
    make_pipe_id,
    make_pipe_id_for_run,
    make_run_method_span_attributes,
    method_identity_of,
)
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

_KEY = "k" * 32
_OTHER_KEY = "q" * 32


def _run_metadata(*, method_id: str | None = None, method_address: str | None = None, capture_pipe_codes: bool | None = None) -> RunMetadata:
    return RunMetadata(
        user_id="user-42",
        pipeline_run_id="run-1",
        storage_scope="tenant/run-1",
        read_scope=None,
        method_id=method_id,
        method_address=method_address,
        capture_pipe_codes=capture_pipe_codes,
    )


class TestPipeIdentity:
    def test_the_method_id_is_the_identity_when_the_run_has_one(self) -> None:
        run_metadata = _run_metadata(method_id="mt_abc", method_address="github.com/acme/methods")

        assert method_identity_of(run_metadata=run_metadata, domain_code="invoices") == "method_id:mt_abc"

    def test_the_package_address_is_the_identity_without_a_method_id(self) -> None:
        run_metadata = _run_metadata(method_address="github.com/acme/methods")

        assert method_identity_of(run_metadata=run_metadata, domain_code="invoices") == "method_address:github.com/acme/methods"

    def test_the_domain_is_the_identity_when_the_run_names_no_method(self) -> None:
        assert method_identity_of(run_metadata=_run_metadata(), domain_code="invoices") == "domain:invoices"

    def test_the_same_pipe_of_the_same_method_gets_the_same_id(self) -> None:
        first = make_pipe_id(key=_KEY, method_identity="method_id:mt_abc", pipe_ref="invoices.extract")
        second = make_pipe_id(key=_KEY, method_identity="method_id:mt_abc", pipe_ref="invoices.extract")

        assert first == second
        assert len(first) == PIPE_ID_HEX_LENGTH

    @pytest.mark.parametrize(
        ("key", "method_identity", "pipe_ref"),
        [
            (_OTHER_KEY, "method_id:mt_abc", "invoices.extract"),
            (_KEY, "method_id:mt_xyz", "invoices.extract"),
            (_KEY, "method_id:mt_abc", "invoices.summarize"),
            (_KEY, "method_id:mt_abc", "receipts.extract"),
        ],
    )
    def test_another_key_method_or_pipe_gets_another_id(self, key: str, method_identity: str, pipe_ref: str) -> None:
        reference = make_pipe_id(key=_KEY, method_identity="method_id:mt_abc", pipe_ref="invoices.extract")

        assert make_pipe_id(key=key, method_identity=method_identity, pipe_ref=pipe_ref) != reference

    def test_the_id_is_not_a_plain_hash_of_the_pipe(self) -> None:
        """A plain hash of a guessed code would confirm the guess; the keyed digest does not."""
        pipe_id = make_pipe_id(key=_KEY, method_identity="domain:invoices", pipe_ref="invoices.extract")

        for candidate in ("invoices.extract", "domain:invoices\ninvoices.extract", "extract"):
            assert pipe_id != hashlib.sha256(candidate.encode()).hexdigest()[:PIPE_ID_HEX_LENGTH]

    def test_no_key_means_no_pipe_id(self, mocker: MockerFixture) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "get_pipe_id_key", return_value=None)

        assert make_pipe_id_for_run(run_metadata=_run_metadata(method_id="mt_abc"), domain_code="invoices", pipe_ref="invoices.extract") is None

    def test_with_a_key_the_run_gets_the_digest_of_its_method_and_pipe(self, mocker: MockerFixture) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "get_pipe_id_key", return_value=_KEY)

        pipe_id = make_pipe_id_for_run(run_metadata=_run_metadata(method_id="mt_abc"), domain_code="invoices", pipe_ref="invoices.extract")

        assert pipe_id == make_pipe_id(key=_KEY, method_identity="method_id:mt_abc", pipe_ref="invoices.extract")

    def test_the_span_attributes_are_absent_when_there_is_nothing_to_say(self) -> None:
        assert make_run_method_span_attributes(run_metadata=_run_metadata(), pipe_id=None) == {}

    def test_the_span_attributes_carry_the_method_the_pipe_and_the_setting(self) -> None:
        attributes = make_run_method_span_attributes(run_metadata=_run_metadata(method_id="mt_abc", capture_pipe_codes=False), pipe_id="abc")

        assert attributes == {
            PipelexSpanAttr.RUN_METHOD_ID: "mt_abc",
            PipelexSpanAttr.PIPE_ID: "abc",
            PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES: False,
        }

    def test_the_package_address_never_rides_a_span(self) -> None:
        attributes = make_run_method_span_attributes(run_metadata=_run_metadata(method_address="github.com/acme/methods"), pipe_id=None)

        assert "github.com/acme/methods" not in attributes.values()
