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
    # with the method, and `/v1/start` fetches the dependency and runs. Built from the item
    # `resolve_crate_from_method_dir`'s refusal carries on 2026-10-18, in the shape that predates the standard, which a
    # runner answering `validation_errors` alone sends.
    UNSHIPPED_ADDRESS_DEPENDENCY: ClassVar[str] = (
        '{"is_valid": false, "validation_errors": [{"category": "pipe_validation", "error_type": "unresolved_package_dependency", '
        '"pipe_code": "score_invoice", "domain_code": "invoicing", "source": "bundle.mthds", '
        '"field_path": "pipe.score_invoice.steps[0].pipe", "missing_pipe_code": "github.com/mthds/scoring-lib/scoring->scoring.score", '
        '"message": "In-memory resolve cannot load address-based dependency '
        "'github.com/mthds/scoring-lib/scoring' from the host filesystem; provide the dependency contents in the request or "
        'use directory-based resolution."}], "message": "The method does not validate."}'
    )
    # The same verdict from a runner speaking the standard, whose items are its problem's `errors`. The empty
    # `validation_errors` is there only because the SDK model this package pins requires that member.
    UNSHIPPED_ADDRESS_DEPENDENCY_PROBLEM_ITEMS: ClassVar[str] = (
        '{"is_valid": false, "validation_errors": [], "errors": [{"code": "method.dependency_missing", "detail": "The method '
        "depends on the package 'github.com/mthds/scoring-lib/scoring', which is not available here (reason: not_found).\", "
        '"params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", "reason": "not_found"}, '
        '"location": {"pipe": "score_invoice", "field": "pipe.score_invoice.steps[0].pipe", "file": "bundle.mthds"}}], '
        '"message": "The method does not validate."}'
    )
    # The same verdict from a runner answering both members, whose `errors` item this client cannot read (it gives no
    # `detail`): its `validation_errors` still name the package.
    UNSHIPPED_ADDRESS_DEPENDENCY_UNREADABLE_PROBLEM_ITEMS: ClassVar[str] = (
        '{"is_valid": false, "validation_errors": [{"category": "pipe_validation", "error_type": "unresolved_package_dependency", '
        '"pipe_code": "score_invoice", "source": "bundle.mthds", "missing_pipe_code": "github.com/mthds/scoring-lib/scoring->scoring.score", '
        '"message": "In-memory resolve cannot load address-based dependency \'github.com/mthds/scoring-lib/scoring\'."}], '
        '"errors": [{"code": "method.dependency_missing", "params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", '
        '"reason": "not_found"}}], "message": "The method does not validate."}'
    )
    # A package the method calls that was found in a cycle: the method's own fault, which no fetch cures.
    DEPENDENCY_CYCLE_PROBLEM_ITEMS: ClassVar[str] = (
        '{"is_valid": false, "validation_errors": [], "errors": [{"code": "method.dependency_missing", "detail": "The method '
        "depends on the package 'github.com/mthds/scoring-lib/scoring', which is not available here (reason: cycle).\", "
        '"params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", "reason": "cycle"}, '
        '"location": {"pipe": "score_invoice", "file": "bundle.mthds"}}], "message": "The method does not validate."}'
    )
    # An item quoting the words of that refusal that no stage coded as a missing dependency: the method's own fault.
    ADDRESS_DEPENDENCY_WORDS_ONLY: ClassVar[str] = (
        '{"is_valid": false, "validation_errors": [{"category": "blueprint_validation", "source": "bundle.mthds", '
        '"message": "In-memory resolve cannot load address-based dependency \'github.com/mthds/scoring-lib/scoring\'."}], '
        '"message": "The method does not validate."}'
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
