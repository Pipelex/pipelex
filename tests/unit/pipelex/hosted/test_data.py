"""Shared data for the unit tests of `pipelex/hosted/`: a captured pipe-io descriptor and the problem documents of hosted refusals."""

from typing import ClassVar


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
    """Problem documents the hosted plane answers a refused request with, as they come off the wire."""

    # The platform's own refusal of a key, authored in front of the runner: no `user_action`.
    UNAUTHORIZED: ClassVar[str] = (
        '{"type":"https://docs.pipelex.com/latest/errors/unauthorized/","title":"Unauthorized","status":401,'
        '"detail":"Invalid or expired API key.","instance":"/v1/start","code":"unauthorized"}'
    )
    UNAUTHORIZED_DETAIL: ClassVar[str] = "Invalid or expired API key."

    # The runner's refusal of a bundle at load, with its own next step.
    INVALID_BUNDLE: ClassVar[str] = (
        '{"type":"https://docs.pipelex.com/latest/errors/validate-bundle-error/","title":"Validate bundle","status":422,'
        "\"detail\":\"Pipe 'draft_pitch' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck\","
        '"instance":"/v1/start","request_id":"req_a3dd6900-7909-48d3-b551-0140e73ac7fc","error_domain":"input",'
        '"retryable":false,"error_type":"ValidateBundleError",'
        '"user_action":{"kind":"change_input","detail":"Edit the bundle as each validation error says"}}'
    )
    INVALID_BUNDLE_DETAIL: ClassVar[str] = "Pipe 'draft_pitch' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck"
    INVALID_BUNDLE_NEXT_STEP: ClassVar[str] = "Edit the bundle as each validation error says"

    # A server fault with nothing to advise.
    SERVER_FAULT: ClassVar[str] = '{"title":"Internal Server Error","status":500,"detail":"Unexpected failure.","request_id":"req_42"}'


class HostedVersions:
    """`GET /v1/version` answers: the hosted API's, which serves the durable run lifecycle, as the dev API gave it on 2026-10-07."""

    HOSTED: ClassVar[str] = (
        '{"protocol_version":"0.1.0","implementation":"pipelex-hosted","implementation_version":"0.30.0","runtime_version":null,'
        '"extensions":["runs","method_id","method_ref"]}'
    )
