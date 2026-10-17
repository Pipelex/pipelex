"""The read scope's check: a scoped run reads only its own storage prefix, and never the local disk."""

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.errors.security_target import SecurityTargetClass
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
        # The security event names the class of what was refused, never the key.
        assert exc_info.value.security_target_class == SecurityTargetClass.FOREIGN_STORAGE_KEY

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
        # A path on the server's disk, or a scheme the run does not read, is a refused scheme to the security event.
        assert exc_info.value.security_target_class == SecurityTargetClass.SCHEME

    @pytest.mark.parametrize(
        ("reason", "target_class", "words"),
        [
            (UriReadRefusalReason.FOREIGN_STORAGE_KEY, SecurityTargetClass.FOREIGN_STORAGE_KEY, "foreign storage"),
            (UriReadRefusalReason.LOCAL_PATH, SecurityTargetClass.SCHEME, "local"),
        ],
    )
    def test_the_sentence_reads_the_target_in_words_while_the_event_keeps_its_class(
        self, reason: UriReadRefusalReason, target_class: SecurityTargetClass, words: str
    ) -> None:
        # The security event is searched by its enum; the caller reads the problem's sentence, which names the target in words.
        as_input = UriReadRefusedError("refused", reason=reason).with_params(input="photo")
        as_method = UriReadRefusedError("refused", reason=reason).with_error_code(CoreCode.SECURITY_METHOD_URL_REFUSED).with_params(pipe="describe")

        assert as_input.security_target_class == target_class
        assert as_input.to_problem(view=ProblemView.CALLER).detail == (
            f"The URL of the input 'photo' points at a {words} target, which a security rule forbids (reason: {reason.desc})."
        )
        assert as_method.to_problem(view=ProblemView.CALLER).detail == (
            f"Pipe 'describe' names a URL that points at a {words} target, which a security rule forbids (reason: {reason.desc})."
        )

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

    def test_the_refusal_is_an_input_error_answered_as_a_422_quoting_no_uri(self) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            authorize_uri_read(uri="/etc/passwd", read_scope=READ_SCOPE, position="the input 'photo'")
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.SECURITY_INPUT_URL_REFUSED
        assert caller.domain == ProblemDomain.INPUT
        assert error_code_spec(CoreCode.SECURITY_INPUT_URL_REFUSED).status == 422
        assert "/etc/passwd" not in str(caller.to_wire())
        operator = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert "the input 'photo'" in operator.diagnostics.message
        assert "/etc/passwd" not in operator.diagnostics.message

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
