"""The read scope's check: a scoped run reads only its own storage prefix, and never the local disk."""

import pytest

from pipelex.base_exceptions import DisclosureMode, ErrorDomain
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError
from pipelex.tools.uri.uri_read_scope import UriReference, authorize_uri_read, authorize_uri_reads

READ_SCOPE = "org_abc"


class TestAuthorizeUriRead:
    @pytest.mark.parametrize(
        "uri",
        [
            "pipelex-storage://org_abc/assets/photo.png",
            "pipelex-storage://org_abc/mt_1/run_9/generated/image.png",
            "https://example.com/photo.png",
            "http://example.com/photo.png",
            "data:image/png;base64,iVBORw0KGgo=",
        ],
    )
    def test_scoped_run_reads_what_the_rule_allows(self, uri: str) -> None:
        authorize_uri_read(uri=uri, read_scope=READ_SCOPE, position="image 1 of the prompt")

    @pytest.mark.parametrize(
        "uri",
        [
            "pipelex-storage://org_other/assets/secret.png",
            # A string prefix of the key's first segment is not a segment prefix.
            "pipelex-storage://org_abcdef/assets/secret.png",
            "pipelex-storage://org_ab/assets/secret.png",
            # Dot segments and empty segments, wherever they sit: the local provider resolves a key against a directory.
            "pipelex-storage://org_abc/../org_other/secret.png",
            "pipelex-storage://org_abc/./assets/photo.png",
            "pipelex-storage://org_abc//assets/photo.png",
            "pipelex-storage:///org_abc/assets/photo.png",
            "pipelex-storage://org_abc/assets/",
            # A backslash is a separator on Windows.
            "pipelex-storage://org_abc/..\\org_other\\secret.png",
            # The scope itself names no object.
            "pipelex-storage://org_abc",
            "pipelex-storage://",
        ],
    )
    def test_scoped_run_refuses_a_key_outside_its_scope(self, uri: str) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            authorize_uri_read(uri=uri, read_scope=READ_SCOPE, position="image 1 of the prompt")
        assert exc_info.value.reason == UriReadRefusalReason.FOREIGN_STORAGE_KEY

    @pytest.mark.parametrize(
        "uri",
        [
            "/etc/passwd",
            "relative/photo.png",
            "photo.png",
            "file:///etc/passwd",
            "~/photo.png",
            # A scheme `resolve_uri` does not know is taken for a local path, and refused as one.
            "s3://bucket/key.png",
            # A data URL without its base64 marker is not one.
            "data:image/png,rawbytes",
        ],
    )
    def test_scoped_run_refuses_a_local_path(self, uri: str) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            authorize_uri_read(uri=uri, read_scope=READ_SCOPE, position="the input 'photo'")
        assert exc_info.value.reason == UriReadRefusalReason.LOCAL_PATH

    def test_a_multi_segment_scope_compares_every_segment(self) -> None:
        authorize_uri_read(uri="pipelex-storage://org_abc/team_1/x.png", read_scope="org_abc/team_1", position="p")
        with pytest.raises(UriReadRefusedError):
            authorize_uri_read(uri="pipelex-storage://org_abc/team_2/x.png", read_scope="org_abc/team_1", position="p")

    @pytest.mark.parametrize(
        "uri",
        [
            "pipelex-storage://org_other/assets/secret.png",
            "pipelex-storage://org_abc/../org_other/secret.png",
            "/etc/passwd",
            "file:///etc/passwd",
            "https://example.com/photo.png",
        ],
    )
    def test_an_unscoped_run_reads_everything(self, uri: str) -> None:
        authorize_uri_read(uri=uri, read_scope=None, position="image 1 of the prompt")

    def test_the_refusal_names_the_position_and_quotes_neither_the_uri_nor_the_scope(self) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            authorize_uri_read(uri="pipelex-storage://org_other/assets/secret.png", read_scope=READ_SCOPE, position="image 2 of the prompt")
        message = str(exc_info.value)
        assert "image 2 of the prompt" in message
        assert "org_other" not in message
        assert "secret.png" not in message
        assert READ_SCOPE not in message

    def test_the_refusal_is_a_caller_facing_input_error_answered_as_a_422(self) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            authorize_uri_read(uri="/etc/passwd", read_scope=READ_SCOPE, position="the input 'photo'")
        error_report = exc_info.value.to_error_report()
        assert error_report.error_domain == ErrorDomain.INPUT
        assert error_report.http_status == 422
        strict = error_report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "the input 'photo'" in strict["message"]
        assert "/etc/passwd" not in strict["message"]

    def test_the_list_form_refuses_the_first_reference_the_scope_does_not_allow(self) -> None:
        uri_references = [
            UriReference(uri="pipelex-storage://org_abc/assets/ok.png", position="image 1 of the prompt"),
            UriReference(uri="pipelex-storage://org_other/assets/secret.png", position="image 2 of the prompt"),
            UriReference(uri="/etc/passwd", position="image 3 of the prompt"),
        ]
        with pytest.raises(UriReadRefusedError) as exc_info:
            authorize_uri_reads(uri_references=uri_references, read_scope=READ_SCOPE)
        assert "image 2 of the prompt" in str(exc_info.value)

    def test_the_list_form_reads_nothing_from_an_empty_list(self) -> None:
        authorize_uri_reads(uri_references=[], read_scope=READ_SCOPE)
