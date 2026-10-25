"""Shared data for the unit tests of `pipelex/hosted/`: a captured pipe-io descriptor and the problem documents of hosted refusals."""

import json
from typing import Any, ClassVar


class HostedDescriptors:
    """Input-form descriptors as the dev API's `POST /v1/pipe-io` answers them.

    `MIXED_FILE_POSITIONS` was captured on 2026-10-07 from `https://api-dev.pipelex.com` for a probe bundle whose
    entry pipe takes a structure carrying an optional nested image, a document, a text and a list of images: every
    kind of position the anchoring walk has to tell apart, the optional nested file included.
    """

    MIXED_FILE_POSITIONS_PIPE_REF: ClassVar[str] = "hosted_probe.summarize_report"
    MIXED_FILE_POSITIONS: ClassVar[str] = (
        '{"fields": [{"kind": "object", "name": "report", "concept_ref": "hosted_probe.Report", '
        '"description": "A report with a cover image and attachments", "required": true, "presence": "plain", "gating": true, '
        '"fields": [{"kind": "text", "name": "title", "description": "The title", "required": true}, '
        '{"kind": "image", "name": "cover", "concept_ref": "native.Image", "description": "The cover", "required": false}]}, '
        '{"kind": "document", "name": "document", "concept_ref": "native.Document", "description": "A document", "required": true, '
        '"presence": "plain", "gating": true}, '
        '{"kind": "prose", "name": "notes", "concept_ref": "native.Text", "description": "A text", "required": true, '
        '"presence": "plain", "gating": true}, '
        '{"kind": "list", "name": "pages", "concept_ref": "native.Image", "description": "An image", "required": true, '
        '"presence": "plain", "gating": false, "item": {"kind": "image", "concept_ref": "native.Image", "description": "An image", '
        '"required": true}}]}'
    )

    TEXT_ONLY_PIPE_REF: ClassVar[str] = "text_stats.analyze_text"
    TEXT_ONLY: ClassVar[str] = (
        '{"fields": [{"kind": "prose", "name": "text", "concept_ref": "native.Text", "description": "A text", "required": true, '
        '"presence": "plain", "gating": true}]}'
    )


class HostedRefusals:
    """Answers the hosted API, or the edge in front of it, refuses a request with, as they come off the wire."""

    # The runner's refusal of a method at load, a problem document in the caller's view listing its faults.
    INVALID_METHOD_ITEMS: ClassVar[list[dict[str, Any]]] = [
        {
            "code": "model.unknown",
            "detail": "The method names the llm model 'gpt-5.1', which no catalog knows.",
            "params": {"model": "gpt-5.1", "model_type": "llm"},
            "location": {"pipe": "draft_pitch", "field": "model", "file": "bundle.mthds"},
            "suggestions": ["gpt-5.5"],
        }
    ]
    INVALID_METHOD_NEXT_STEP: ClassVar[str] = "Fix each fault the problem's errors list, then validate the method again."
    INVALID_METHOD: ClassVar[str] = json.dumps(
        {
            "type": "https://mthds.ai/errors/method.invalid",
            "title": "The method does not validate",
            "status": 422,
            "detail": "The method does not validate.",
            "code": "method.invalid",
            "domain": "method",
            "retry": "no",
            "next_step": {"kind": "change_method", "detail": INVALID_METHOD_NEXT_STEP},
            "errors": INVALID_METHOD_ITEMS,
            "request_id": "01M55PINVALIDMETHOD000000",
        }
    )
    # The hosted plane's refusal of a key it does not know, a problem document with its own reason and next step.
    INVALID_KEY_DETAIL: ClassVar[str] = "The API key is not valid."
    INVALID_KEY_NEXT_STEP: ClassVar[str] = "Create a new API key on app.pipelex.com, then send the request again."
    INVALID_KEY: ClassVar[str] = json.dumps(
        {
            "type": "https://mthds.ai/errors/auth.invalid_credential",
            "title": "The credential was refused",
            "status": 401,
            "detail": INVALID_KEY_DETAIL,
            "code": "auth.invalid_credential",
            "domain": "account",
            "retry": "no",
            "next_step": {"kind": "check_credentials", "detail": INVALID_KEY_NEXT_STEP},
            "request_id": "01M55PINVALIDKEY000000000",
        }
    )
    # The hosted plane's rate limit, a problem document whose delay rides its `Retry-After` header.
    RATE_LIMITED: ClassVar[str] = json.dumps(
        {
            "type": "https://mthds.ai/errors/account.rate_limited",
            "title": "The account is over its request rate",
            "status": 429,
            "detail": "Too many runs started in the last minute.",
            "code": "account.rate_limited",
            "domain": "account",
            "retry": "yes",
            "next_step": {"kind": "wait", "detail": "Wait for the rate window to pass, then send the request again."},
        }
    )
    # The hosted edge's bare refusals, which are no problem document: of a request its authorizer did not let through,
    # of a route no server behind it serves, and a gateway's error page.
    BARE_UNAUTHORIZED: ClassVar[str] = '{"message":"Unauthorized"}'
    BARE_FORBIDDEN: ClassVar[str] = '{"message":"Forbidden"}'
    BARE_NOT_FOUND: ClassVar[str] = '{"detail":"Not Found"}'
    BARE_BAD_REQUEST: ClassVar[str] = '{"message":"Bad Request"}'
    GATEWAY_PAGE: ClassVar[str] = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1></body></html>"


class HostedVersions:
    """`GET /v1/version` answers: the hosted API's, which serves the durable run lifecycle, as the dev API gave it on 2026-10-07."""

    HOSTED: ClassVar[str] = (
        '{"protocol_version":"0.1.0","implementation":"pipelex-hosted","implementation_version":"0.30.0","runtime_version":null,'
        '"extensions":["runs","method_id","method_ref"]}'
    )
    #: A bare runner's, which keeps no runs, so a run on it takes the blocking `POST /v1/execute`.
    BARE_RUNNER: ClassVar[str] = '{"protocol_version":"0.1.0","implementation":"pipelex-api","implementation_version":"0.76.0"}'
    #: The hosted API's with a blob store, so a tree past the inline threshold travels by the hash of each file.
    HOSTED_WITH_BLOB_STORE: ClassVar[str] = (
        '{"protocol_version":"0.1.0","implementation":"pipelex-hosted","implementation_version":"0.30.0","runtime_version":null,'
        '"blob_store":true,"extensions":["runs","method_id","method_ref"]}'
    )


class HostedPipeIoVerdicts:
    """`POST /v1/pipe-io` invalid verdicts, as the runner's crate core builds them in the caller's view."""

    # A method calling a package by its address that the request did not ship: pipe-io loads only the packages shipped
    # with the method, and `/v1/start` fetches the dependency and runs. Its item is coded `method.dependency_missing`.
    UNSHIPPED_ADDRESS_DEPENDENCY: ClassVar[str] = (
        '{"is_valid": false, "errors": [{"code": "method.dependency_missing", "detail": "The method '
        "depends on the package 'github.com/mthds/scoring-lib/scoring', which is not available here (reason: not_found).\", "
        '"params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", "reason": "not_found"}, '
        '"location": {"pipe": "score_invoice", "field": "pipe.score_invoice.steps[0].pipe", "file": "bundle.mthds"}}], '
        '"message": "The method does not validate."}'
    )
    # The same verdict with an item before it that this client cannot read, since it gives no `detail`: the SDK skips it,
    # and the item after it still names the package.
    UNSHIPPED_ADDRESS_DEPENDENCY_AFTER_AN_UNREADABLE_ITEM: ClassVar[str] = (
        '{"is_valid": false, "errors": [{"code": "method.dependency_missing", "params": {"kind": "package", '
        '"name": "github.com/mthds/other-lib/other", "reason": "not_found"}}, {"code": "method.dependency_missing", "detail": "The method '
        "depends on the package 'github.com/mthds/scoring-lib/scoring', which is not available here (reason: not_found).\", "
        '"params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", "reason": "not_found"}}], '
        '"message": "The method does not validate."}'
    )
    # A package the method calls that was found in a cycle: the method's own fault, which no fetch cures.
    DEPENDENCY_CYCLE: ClassVar[str] = (
        '{"is_valid": false, "errors": [{"code": "method.dependency_missing", "detail": "The method '
        "depends on the package 'github.com/mthds/scoring-lib/scoring', which is not available here (reason: cycle).\", "
        '"params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", "reason": "cycle"}, '
        '"location": {"pipe": "score_invoice", "file": "bundle.mthds"}}], "message": "The method does not validate."}'
    )
    # An item quoting the words of that refusal under another code: the method's own fault.
    ADDRESS_DEPENDENCY_WORDS_ONLY: ClassVar[str] = (
        '{"is_valid": false, "errors": [{"code": "method.schema_violation", "detail": "The declaration at \'pipe.score_invoice\' '
        "breaks a rule of the language (In-memory resolve cannot load address-based dependency 'github.com/mthds/scoring-lib/scoring').\", "
        '"params": {"field_path": "pipe.score_invoice", "finding": "In-memory resolve cannot load address-based dependency '
        '\'github.com/mthds/scoring-lib/scoring\'"}, "location": {"file": "bundle.mthds"}}], "message": "The method does not validate."}'
    )
    # A method whose model no catalog knows, with the item locating the fault by its file.
    UNKNOWN_MODEL: ClassVar[str] = (
        '{"is_valid": false, "errors": [{"code": "model.unknown", "detail": "The method names the llm model \'gpt-5.1\', which '
        'no catalog knows.", "params": {"model": "gpt-5.1", "model_type": "llm"}, "location": {"pipe": "step2", "field": "model", '
        '"file": "lib/b.mthds"}, "suggestions": ["gpt-5.5"]}], "message": "Bundle does not load"}'
    )


class HostedPipeIoRefusals:
    """`POST /v1/pipe-io` refusals, as the runner answers them in the caller's view."""

    # A form of a field the runtime does not accept: a refusal no hosted run reads as anything but the hosted API's own.
    UNSUPPORTED_FORM: ClassVar[str] = (
        '{"type": "https://mthds.ai/errors/request.unsupported", "title": "The request uses a form this runtime does not accept", '
        '"status": 422, "detail": "This runtime does not accept the form the request\'s field \'extra\' uses (reason: '
        'hosted_only_extension).", "code": "request.unsupported", "domain": "input", "retry": "no", "next_step": {"kind": '
        '"change_input", "detail": "Send the field \'extra\' in a form this runtime accepts, then send the request again."}, '
        '"params": {"field": "extra", "reason": "hosted_only_extension"}}'
    )
