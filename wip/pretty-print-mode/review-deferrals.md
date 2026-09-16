---
status: active
item: L-260915-c66b8a
---

# Deferred review findings — `feature/Pretty-print-mode`

What the round-1 `/rev` pass at profile 5 found, confirmed, and deliberately did not fix. The bar was `open`: confirmed defects that are real and matter, plus improvements that genuinely matter. Everything below is real and did not clear that bar, so it is recorded here rather than dropped. Nothing here was invented by the pass — each line is a reviewer's finding that a verifier then read the code for.

Two findings left this document for a ledger item instead, because they are not this branch's to fix: the `pipelex-server` sweep miss and the stuff viewer's attribute-injection XSS.

## Verified, deferred

These were sent to the verifier and confirmed. They are deferred on importance, not on doubt.

- **`escapeHtml` does not escape the double quote** — filed as a ledger item rather than left here, since it is a live XSS on a page that opens with no CSP. Pre-existing; the branch does not touch the file.
- **`isSafeDisplayUrl` is a scheme check and nothing more.** Any http(s) host and any `file://` path from a model-controlled field is accepted, and the url is assigned to `img.src` / `embed.src`. Opening a stuff node therefore fires an unattended GET to a host the model chose, and preview is now the default tab. Not a cross-trust-boundary leak while the viewer's own user is reading their own files, but it stops being benign the moment a graph page is served over http(s) or opened in a webview.
- **`[empty list]` is swallowed from every panel title.** Rich's tag regex accepts a tag opening with a lowercase letter, so the marker parses as a style tag and is dropped; `[1 item]` and `[3 items]` survive only because they start with a digit. The size marker therefore shows for every list except the empty one — the case a reader most needs. Pre-existing in the Rich path, and the new plain title reproduces it faithfully, which is correct parity rather than a second bug. Fixing it means escaping the bracket or writing `(empty list)`, in both paths at once.
- **The per-character wrapping floor.** Content wraps to one character per row below a terminal of about nine columns, because the content width is floored at one. Reachable only from a genuinely tiny terminal or a `COLUMNS` set that small: nothing in the package passes a `console_width` outside tests, and the poor arm passes no width at all. A usable floor of around twenty would close it.
- **The two mermaid data test modules are byte-identical**, same class name included, so this branch applied the same deletions twice. Pre-existing. The risk is the ordinary one: an edit lands in one copy and the other keeps passing while asserting the old behaviour.
- **The graph viewer's tab fallback can select a disabled tab.** `updateTabAvailability` returns `json` without consulting whether the JSON tab is itself disabled, so a stuff node with no JSON data and no previewable url gets a disabled button marked active over a "No JSON data available" body. Reachable from a content class that declares no fields.

## Raised, not verified

Sorted as deferrals on the reviewers' word alone — the bar would not have fixed them even read as true, so no verifier time was spent. Treat each as a candidate, not a fact.

- **Rendering policy in the domain model.** `StuffContent` reads the process-global printer mode and repeats a dispatch the printer already owns, so a fourth mode would have to be implemented in two layers. A lazy or dual rendering contract on the printer would keep the silent short-circuit while centralising the choice. This is a design trade-off, which is a thing to decide deliberately rather than to patch inside a review round.
- **Neither `match` on the mode has an exhaustiveness guard**, so a fourth member would fall through silently in both. All three members are handled today, so there is no live bug.
- **One unbuffered stderr write per wrapped line** — the poor printer now prints real content, so a large output issues hundreds of writes where it used to issue one. Joining the rows and printing once would fix it.
- **The poor path loses the truncation the Rich path applies** to dicts and models, so a call that dumps a payload with embedded base64 prints it whole where Rich clips it. Pre-existing for dicts, since a dict was never a Rich renderable; what the branch changes is the volume.
- **A `Text`-wrapped url takes a full Console render** in the poor mode, because the string check misses it. Off the hot path.
- **Falsy width guards swallow an explicit zero**, using the terminal size instead.
- **Dead code**: `pretty_svg` (the exact twin of the `pretty_html` this branch deletes), `render_stuff_content_viewer`, and the JS `getHtmlTabLabel` whose labelling the diff inlined. Three dead graph test fixtures were left behind too, and a third copy of the ANSI-stripping helper now exists in a directory that already has a conftest.
- **Docstrings in the agent CLI factory claim the pinned silent mode "neutralizes `pretty_print` entirely."** That was never quite true and is less so now; the discipline holds because nothing pretty-prints after those teardowns, not because the claim is.
- **The migration ledger's `introduced_in` is unchecked**, so a release cut under a different number leaves it silently wrong. A process guard exists in the release skill.
- **Three e2e migration assertions were loosened** from an exact step list to a first-element check. The loosening is itself necessary, but no test now pins the complete list, and none names the new ledger entry.
- **No test loads a pre-0.59 graph spec**, so the documented refusal is unexercised and a future change to the model's strictness would contradict the changelog without failing anything.
- **The mode-config test re-implements the conftest boot** by hand, so the two can diverge silently.
- **The rolling-deploy window on DynamoDB**: an old-image worker writing events a newer assembler reads back. Weigh against the fact that Temporal has not shipped to production.
- **A Mermaid label escaping gap** — the escaper turns `<` and `>` into entities but not `&`, so a label already spelling an entity survives to be decoded. The reviewer did not execute this path, and Mermaid's own security level is the remaining barrier.
- **The CSP nonce on the interactive page buys nothing**, since the page depends on inline handlers and a nonce makes `'unsafe-inline'` ignored for scripts. The two viewers are inconsistent about it.

## Cleared

Worth recording so the next round does not re-litigate them. The `@3` migration golden rewrite is legitimate — it was the head link when it was rewritten, and the rule is that the head link tracks while every link below it is frozen; both gates pass and the reserved-key derivation is a path-set operation blind to default values. Two reviewers disagreed on this and the verified analysis won. Removing DOMPurify is safe on its own terms: a full sink audit of the interactive page found no attacker-controlled string reaching any `innerHTML` in the page's own JS. The exposure it appeared to cover was one layer up, in the JSON-embedding filter, which DOMPurify never covered either and which this branch fixed.
