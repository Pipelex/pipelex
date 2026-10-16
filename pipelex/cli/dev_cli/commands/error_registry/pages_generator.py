"""The generator of the error code pages under ``docs/errors/``: their index, and one page per Pipelex code.

A code's page is ``docs/errors/<prefix>/<family>/<name>.md``, one directory per segment but the last, as the
MTHDS standard lays out the core codes' pages, which MkDocs serves at ``/<version>/errors/<prefix>/<family>/<name>/``.
The type URI, ``https://docs.pipelex.com/errors/<code>``, names no version, so it reaches the page through the
redirect stub the documentation's deployment writes at the site's root
(:mod:`pipelex.cli.dev_cli.commands.error_registry.type_redirects`).

The pages follow the MTHDS standard's pages for the core codes, and link to the standard's documentation for
what a domain, a retry verdict and a step are. They are committed, so that the documentation builds from the
repository as it stands, and the test suite fails when they are not what this generator writes.
"""

from __future__ import annotations

import json
import posixpath
import re
from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.error_registry.registry_source import INDEX_PAGE
from pipelex.errors.registry.registry_document import (
    RegistryDomain,
    RegistryItemType,
    RegistryParam,
    RegistryParamType,
    RegistryRaisedAs,
    RegistryRetry,
)

if TYPE_CHECKING:
    from pipelex.errors.registry.registry_document import ErrorRegistryDocument, RegistryEntry

# The pages of the MTHDS standard the generated ones link to.
MTHDS_DOCS_URL = "https://mthds.ai/latest"
MTHDS_PROTOCOL_URL = f"{MTHDS_DOCS_URL}/spec/protocol/"
MTHDS_REGISTRY_URL = f"{MTHDS_DOCS_URL}/spec/error-registry/"
MTHDS_CORE_CODES_URL = f"{MTHDS_DOCS_URL}/errors/"
RELEASES_URL = "https://github.com/Pipelex/pipelex/releases"

# The page of this documentation that describes how the registry is maintained.
CONTRIBUTE_PAGE = "contribute/error-registry.md"
# The section of this documentation that says how far errors carry the registry's codes.
ERROR_MODEL_SECTION = "under-the-hood/error-model.md#error-codes-and-the-pipelex-error-registry"


def _domain_action(*, domain: RegistryDomain) -> str:
    """Who acts, per domain, after the protocol's domain table."""
    match domain:
        case RegistryDomain.INPUT:
            return "the caller acts, by changing the request or its inputs"
        case RegistryDomain.METHOD:
            return "the method's author acts, by changing the method"
        case RegistryDomain.ACCOUNT:
            return "the account's owner acts"
        case RegistryDomain.OPERATOR:
            return "whoever runs the runtime acts"
        case RegistryDomain.RUNTIME:
            return "nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem"


def _domain_actor(*, domain: RegistryDomain) -> str:
    """The reader the actor's step is aimed at."""
    match domain:
        case RegistryDomain.INPUT:
            return "the caller"
        case RegistryDomain.METHOD:
            return "the method's author"
        case RegistryDomain.ACCOUNT:
            return "the account's owner"
        case RegistryDomain.OPERATOR:
            return "whoever runs the runtime"
        case RegistryDomain.RUNTIME:
            return "whoever made the call"


def _retry_meaning(*, retry: RegistryRetry) -> str:
    match retry:
        case RegistryRetry.NO:
            return "repeating the operation fails the same way"
        case RegistryRetry.YES:
            return "repeating the operation may succeed, after `retry_after` seconds when the problem gives it"
        case RegistryRetry.OUTCOME_UNKNOWN:
            return "the operation may already have taken effect, so its outcome is learned before anything is repeated"


def _raised_as_meaning(*, raised_as: RegistryRaisedAs) -> str:
    match raised_as:
        case RegistryRaisedAs.PROBLEM:
            return "a problem document, sent as the body of an HTTP response or kept in a run's record"
        case RegistryRaisedAs.WARNING:
            return "an item of a validate verdict's `warnings`, which never makes a method invalid"
        case RegistryRaisedAs.CLIENT:
            return "an error a client detects itself, never received from a runner"


def _link(*, page: str, target: str) -> str:
    """The relative link from the page ``page`` to ``target``, both from the documentation's root."""
    path, _, anchor = target.partition("#")
    relative = posixpath.relpath(path, posixpath.dirname(page))
    return f"{relative}#{anchor}" if anchor else relative


def _front_matter(*, title: str, description: str) -> str:
    # A JSON string is a valid YAML double-quoted scalar.
    return f"---\ntitle: {json.dumps(title)}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n"


def _cell(*, text: str) -> str:
    """Text made safe for one cell of a Markdown table."""
    return text.replace("|", "\\|").replace("\n", " ")


def _show_template(*, template: str) -> str:
    """A template as a page shows it: each placeholder as code, a doubled brace as one."""
    shown = re.sub(r"(?<!\{)\{([a-z][a-z0-9_]*)\}(?!\})", r"`{\1}`", template)
    return shown.replace("{{", "{").replace("}}", "}")


def _family_anchor(*, family: str) -> str:
    """The anchor of a family's section on the index, set explicitly so that it never depends on the slug rules."""
    return family.replace(".", "-").replace("_", "-")


def _scalar_type_name(*, scalar_type: RegistryParamType, values: list[str] | None) -> str:
    match scalar_type:
        case RegistryParamType.ENUM:
            return "one of " + ", ".join(f"`{value}`" for value in values or [])
        case (
            RegistryParamType.IDENTIFIER
            | RegistryParamType.INTEGER
            | RegistryParamType.SECONDS
            | RegistryParamType.BYTES
            | RegistryParamType.SHA256
            | RegistryParamType.CALLER_TEXT
            | RegistryParamType.LIST
        ):
            return f"`{scalar_type}`"


def _item_type_name(*, item_type: RegistryItemType) -> str:
    return _scalar_type_name(scalar_type=item_type.item_type, values=item_type.values)


def _param_type_name(*, param: RegistryParam) -> str:
    if param.param_type.is_list and param.items is not None:
        return f"list of {_item_type_name(item_type=param.items)}"
    return _scalar_type_name(scalar_type=param.param_type, values=param.values)


def _status_cell(*, entry: RegistryEntry) -> str:
    if entry.status is not None:
        return f"`{entry.status}`"
    return f"none ({entry.raised_as})"


def render_index_page(*, registry: ErrorRegistryDocument) -> str:
    """The index of the error codes: every Pipelex code by family, each linking to its page."""
    page = INDEX_PAGE
    lines = [
        _front_matter(
            title="Error Codes",
            description="Every Pipelex error code, with its title, domain, retry verdict and HTTP status, each linking to its page.",
        ),
        "# Error Codes",
        "",
        (
            "An error code names a situation a runner or a client can meet, and its type URI is the URL of the code's page. "
            "A code of the MTHDS standard, such as `input.missing`, is a core code, documented with the standard on "
            f"[mthds.ai]({MTHDS_CORE_CODES_URL}) at `https://mthds.ai/errors/<code>`. A code that starts with `pipelex.` names "
            "a situation the standard leaves to its implementations, and has its page here, at "
            f"`{registry.base_url}/<code>`. Each page says what its code means, who must act and what to do, and gives the "
            "code's steps, parameters and templates."
        ),
        "",
        (
            "These pages are generated from the Pipelex error registry, which follows the "
            f"[MTHDS error registry format]({MTHDS_REGISTRY_URL}) under the `{registry.prefix}` prefix the core registry "
            "registers to Pipelex. The registry is published with every Pipelex release, as the release asset "
            f"`pipelex-error-registry.json` on [GitHub]({RELEASES_URL}) and inside the `pipelex` package. This is version "
            f"`{registry.version}` of the registry. [The Error Registry]({_link(page=page, target=CONTRIBUTE_PAGE)}) "
            "describes how it is maintained."
        ),
        "",
        (
            "The registry declares the Pipelex codes, but Pipelex's errors do not carry them yet: an error still reports its "
            "`error_type` and a type URI derived from its class, and giving every error its code is the next step of this "
            f"work, as the [Error Model]({_link(page=page, target=ERROR_MODEL_SECTION)}) describes."
        ),
        "",
    ]
    for family in registry.families:
        name = family.family
        lines.append(f"## {name} {{ #{_family_anchor(family=name)} }}")
        lines.append("")
        lines.append(family.description)
        lines.append("")
        lines.append("| Code | Title | Domain | Retry | Status |")
        lines.append("|---|---|---|---|---|")
        for entry in registry.codes:
            if entry.family != name:
                continue
            lines.append(
                f"| [`{entry.code}`]({_link(page=page, target=entry.page_path)}) "
                f"| {_cell(text=entry.title)} | `{entry.domain}` | `{entry.retry}` | {_status_cell(entry=entry)} |"
            )
        lines.append("")
    return "\n".join(lines)


def _next_steps_intro(*, entry: RegistryEntry) -> str:
    """The sentence above a code's steps, which says who each one is for."""
    actor = _domain_actor(domain=entry.domain)
    step = f"[step]({MTHDS_PROTOCOL_URL}#next-steps)"
    match entry.raised_as:
        case RegistryRaisedAs.WARNING:
            return (
                f"A warning carries no {step} of its own, since it is an item of a validate verdict, so its reader takes "
                f"one of the code's steps: the first when the reader is the domain's actor, {actor}, and the second for "
                "any other reader."
            )
        case RegistryRaisedAs.CLIENT:
            return (
                f"A client that detects this error offers the {step} aimed at whoever reads it: the first when its "
                f"reader is the domain's actor, {actor}, and the second for any other reader."
            )
        case RegistryRaisedAs.PROBLEM:
            return (
                f"A problem carries the {step} aimed at whoever reads it: the first when its reader is the domain's "
                f"actor, {actor}, and the second for any other reader."
            )


def _params_section(*, entry: RegistryEntry) -> list[str]:
    params = entry.params
    if not params:
        return ["This code declares no parameters, so its problems carry no `params`.", ""]
    lines: list[str] = []
    if any(param.optional or param.operator_only for param in params.values()):
        lines.append(
            "A parameter is present on every occurrence of the code unless it is marked optional, and one marked "
            "operator-only reaches only whoever runs the runtime, never a caller."
        )
    else:
        lines.append("Every parameter is present on every occurrence of the code.")
    lines.append("")
    lines.append("| Name | Type | Description |")
    lines.append("|---|---|---|")
    for param_name, param in params.items():
        marks: list[str] = []
        if param.optional:
            marks.append("optional")
        if param.operator_only:
            marks.append("operator-only")
        mark = f" ({', '.join(marks)})" if marks else ""
        lines.append(f"| `{param_name}` | {_param_type_name(param=param)}{mark} | {_cell(text=param.description)} |")
    lines.append("")
    return lines


def render_code_page(*, registry: ErrorRegistryDocument, entry: RegistryEntry) -> str:
    """The page of one code."""
    code = entry.code
    page = entry.page_path
    index = _link(page=page, target=INDEX_PAGE)
    family_description = next(family.description for family in registry.families if family.family == entry.family)
    lines = [
        _front_matter(title=code, description=f"{entry.title}: what the Pipelex error code {code} means, who must act and what to do."),
        f"# {code}",
        "",
        f"**{entry.title}**",
        "",
        "| | |",
        "|---|---|",
        f"| Type | `{registry.type_uri(code=code)}` |",
        f"| Family | [`{entry.family}`]({index}#{_family_anchor(family=entry.family)}): {_cell(text=family_description)} |",
        f"| [Domain]({MTHDS_PROTOCOL_URL}#domain-who-must-act) | `{entry.domain}`: {_domain_action(domain=entry.domain)} |",
        f"| [Retry]({MTHDS_PROTOCOL_URL}#retry) | `{entry.retry}`: {_retry_meaning(retry=entry.retry)} |",
        f"| HTTP status | {_status_cell(entry=entry)} |",
        f"| Raised as | {_raised_as_meaning(raised_as=entry.raised_as)} |",
        "",
        "## What it means",
        "",
        entry.meaning,
        "",
        "## What to do",
        "",
        entry.what_to_do,
        "",
        "## Next steps",
        "",
        _next_steps_intro(entry=entry),
        "",
        "| Reader | Kind | Detail |",
        "|---|---|---|",
        f"| The domain's actor | `{entry.steps.actor.kind}` | {_cell(text=_show_template(template=entry.steps.actor.detail))} |",
        f"| Any other reader | `{entry.steps.other.kind}` | {_cell(text=_show_template(template=entry.steps.other.detail))} |",
        "",
        "## Detail",
        "",
        "The problem's `detail` is written from this template, filled with the occurrence's parameters:",
        "",
        f"> {_show_template(template=entry.detail)}",
        "",
        "## Parameters",
        "",
        *_params_section(entry=entry),
        "## See also",
        "",
    ]
    lines.extend(f"- [{reference.title}]({_link(page=page, target=reference.href)})" for reference in entry.see or [])
    lines.append(f"- [The MTHDS error registry format]({MTHDS_REGISTRY_URL}), which describes the members of this page")
    lines.append(f"- [Error Codes]({index}), every Pipelex code")
    lines.append("")
    return "\n".join(lines)


def generated_page_paths(*, registry: ErrorRegistryDocument) -> frozenset[str]:
    """The path of every page :func:`render_pages` writes, from the documentation's root, without rendering them."""
    return frozenset({INDEX_PAGE, *(entry.page_path for entry in registry.codes)})


def render_pages(*, registry: ErrorRegistryDocument) -> dict[str, str]:
    """Every generated page, by its path from the documentation's root."""
    pages = {INDEX_PAGE: render_index_page(registry=registry)}
    for entry in registry.codes:
        pages[entry.page_path] = render_code_page(registry=registry, entry=entry)
    return pages
