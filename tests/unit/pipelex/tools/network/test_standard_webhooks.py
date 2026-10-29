import hashlib
import json
import tomllib
from operator import itemgetter
from pathlib import Path
from typing import Any

import pytest

from pipelex.tools.network.standard_webhooks import decode_webhook_secret, sign_webhook

VECTORS_DIR = Path("tests/data/caller_webhooks")
VECTORS_PATH = VECTORS_DIR / "signature-vectors.json"
VENDORED_RECORD_PATH = VECTORS_DIR / "vendored.toml"


def _signing_cases() -> list[dict[str, Any]]:
    """The vendored vectors' signing cases: calls as a sender signs them."""
    vectors: dict[str, Any] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    signing_cases: list[dict[str, Any]] = vectors["signing"]
    return signing_cases


class TestStandardWebhooks:
    def test_the_vectors_are_the_vendored_copy(self) -> None:
        """The vectors are byte for byte the conformance file vendored.toml records, at its digest."""
        record = tomllib.loads(VENDORED_RECORD_PATH.read_text(encoding="utf-8"))
        vectors_record = record["files"]["signature-vectors.json"]
        assert vectors_record["path"] == "tests/caller_webhooks/fixtures/signature-vectors.json"
        assert len(record["source"]["commit"]) == 40
        assert hashlib.sha256(VECTORS_PATH.read_bytes()).hexdigest() == vectors_record["sha256"]

    def test_the_vectors_cover_one_secret_a_rotation_and_a_body_outside_ascii(self) -> None:
        """The signing cases this module signs are the three the contract names, so none was dropped from the copy."""
        signing_cases = _signing_cases()
        assert {case["name"] for case in signing_cases} >= {"failed_run", "rotation", "non_ascii_body"}
        rotation_case = next(case for case in signing_cases if case["name"] == "rotation")
        assert len(rotation_case["secrets"]) == 2
        non_ascii_case = next(case for case in signing_cases if case["name"] == "non_ascii_body")
        assert not non_ascii_case["body"].isascii()

    @pytest.mark.parametrize("signing_case", _signing_cases(), ids=itemgetter("name"))
    def test_each_signing_case_signs_to_its_header_byte_for_byte(self, signing_case: dict[str, Any]) -> None:
        """Every vendored call signs to exactly its `webhook-signature`, its body's characters outside ASCII as UTF-8 bytes."""
        secret_keys = [decode_webhook_secret(secret=secret) for secret in signing_case["secrets"]]

        signature = sign_webhook(
            secret_keys=secret_keys,
            webhook_id=signing_case["webhook_id"],
            webhook_timestamp=signing_case["webhook_timestamp"],
            body=signing_case["body"].encode("utf-8"),
        )

        assert signature == signing_case["webhook_signature"]

    def test_a_rotation_writes_the_current_secrets_signature_first(self) -> None:
        """During a rotation each secret signs the call, the current one first, separated by a single space."""
        rotation_case = next(case for case in _signing_cases() if case["name"] == "rotation")
        current_key, previous_key = (decode_webhook_secret(secret=secret) for secret in rotation_case["secrets"])
        arguments: dict[str, Any] = {
            "webhook_id": rotation_case["webhook_id"],
            "webhook_timestamp": rotation_case["webhook_timestamp"],
            "body": rotation_case["body"].encode("utf-8"),
        }

        current_signature = sign_webhook(secret_keys=[current_key], **arguments)
        previous_signature = sign_webhook(secret_keys=[previous_key], **arguments)

        assert rotation_case["webhook_signature"] == f"{current_signature} {previous_signature}"

    @pytest.mark.parametrize(
        "secret",
        [
            pytest.param("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=", id="no_prefix"),
            pytest.param("whsec_not base64!", id="not_base64"),
            pytest.param("whsec_", id="no_key"),
            pytest.param("WHSEC_AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=", id="prefix_in_capitals"),
        ],
    )
    def test_a_value_that_is_not_a_whsec_secret_is_refused(self, secret: str) -> None:
        """Only `whsec_` followed by standard base64 of at least one byte is a signing secret."""
        with pytest.raises(ValueError, match="webhook signing secret"):
            decode_webhook_secret(secret=secret)

    def test_signing_needs_a_secret(self) -> None:
        """A call is never sent unsigned: signing under no secret is refused rather than writing an empty header."""
        with pytest.raises(ValueError, match="at least one secret"):
            sign_webhook(secret_keys=[], webhook_id="whd_abc", webhook_timestamp="1792670401", body=b"{}")
