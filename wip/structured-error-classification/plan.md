---
status: active
item: L-260927-086ea4
---

# Plan: a gateway's model_not_allowed refusal says to change the model

The design is `design.md` beside this file. The work happens in the worktree `_pipelex--structured-error-classification`, on the branch `fix/Structured-error-classification`, based on `85729dfd3`. Tests come first: write the failing tests before touching the code they cover. Louis approved this plan for implementation on 2026-09-28.

## Picking it up

- Enter the worktree with `wt open --for L-260927-086ea4`, then run `ledger claim L-260927-086ea4 --renew` from inside it.
- The helpers the tests need already exist in `tests/unit/pipelex/cogt/inference/test_gateway_routing_refusals.py`: `_as_the_portkey_sdk_raises_it`, `_as_the_openai_sdk_raises_it` and `_ORIGIN`. For the Anthropic hop, `anthropic.AsyncAnthropic(api_key=…, base_url=_ORIGIN)._make_status_error_from_response(response)` builds what the SDK raises; for a 412 that is a plain `APIStatusError`.
- For the real-loop module, the earlier probe is a working sketch. Build a real `openai.AsyncOpenAI` or `anthropic.AsyncAnthropic` with `http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))` and `max_retries=0`, wrap it with `from_openai(client, mode=Mode.TOOLS)` or `from_anthropic(client)`, and call `create_with_completion(…, response_model=…, max_retries=make_instructor_schema_retrying(max_attempts=3))`. For an invalid output, return a chat completion whose tool call's arguments fail the schema. The Anthropic SDK release locked here takes an `httpx` client. More recent Anthropic releases insist on `httpx2`, so a future lock move will need the transport changed.
- The campaign's 412 body is `{"error": {"message": "Model us.anthropic.claude-sonnet-4-5-20250929-v1:0 is not allowed for this integration", "type": "model_not_allowed_error", "param": null, "code": null}}`, and its model handle is `claude-4.5-sonnet`.
- `_render_detail` has a single caller, `render_inference_error`, so adding `model_handle` to its signature touches nothing else. It is keyword-only after the existing subject.

## What already landed

The instructor half of the first draft (reading `__cause__` first in `extract_underlying_sdk_exception`, moving the lock, raising the floor, and rewriting the helper and the unwrap docs) landed in pipelex#1289 as `85729dfd3`. It was re-verified against the real instructor 1.17.0 loop; the table is in the design.

## Classify model_not_allowed and pin the instructor wrapper to the real loop

- [ ] Write the failing tests first.
    - Extend `tests/unit/pipelex/cogt/inference/test_gateway_routing_refusals.py`:
        - `model_not_allowed_error` maps to `MODEL_NOT_ALLOWED`;
        - it survives every Extract hop, each exception built through its SDK's own factory: the OpenAI hop through `_make_status_error_from_response(response)`, which takes no `request` argument, the Anthropic hop, the Portkey substrate, and the manifold's httpx hop;
        - it classifies as `CONFIGURATION` / `CHANGE_MODEL`, not retried, with `is_model_not_found` unset;
        - the advice names the model handle and not the wire id;
        - the HTTP status stays 500;
        - the advice survives the pipe boundary.
    - Add the real-loop module of design D4, for example `tests/unit/pipelex/providers/test_instructor_retry_shapes.py`. It drives `from_openai` and `from_anthropic` over `httpx.MockTransport` for the three shapes, and asserts that the recovery returns the exception that ended the loop and that the raised shape is the one `wrap_in_instructor_retry` builds. In the same module, drive the campaign's scenario end to end: the OpenAI completions worker's `_gen_object` over real instructor, the gateway answering 412 with the campaign's body, and the located failure report showing `error_domain: config`, `error_category: configuration` and `user_action.kind: change_model`.
- [ ] Add `GatewayRoutingRefusal.MODEL_NOT_ALLOWED` and its map entry. Rewrite the enum docstring and the map comment per design D1: this member is keyed on the gateway substrate's code and arrives on 412, it has two raise sites (not in the allow-list, or archived), and no vendor collision is possible.
- [ ] Add its arm to `_classify_gateway_routing_refusal`, with a comment tying it to `WRONG_PROTOCOL` and `UNSERVED_CAPABILITY` on why the flag stays unset.
- [ ] Thread `model_handle` from `render_inference_error` through `_render_detail` into `_render_gateway_routing_refusal_detail`, and write this member's advice (design D2). The other members keep ignoring the handle. Update that function's docstring, which says the family names no model, to state this exception and its reason.
- [ ] In `docs/under-the-hood/error-model.md`, add the row to the "When the model cannot be routed" table and a bullet on the unset flag and the handle in the advice. In the "`instructor` Unwrap" section, correct the sentence claiming a `pydantic.ValidationError` lands in `UNKNOWN` (design D5).
- [ ] In `CHANGELOG.md` under Unreleased, add a Fixed entry: a gateway's `model_not_allowed_error` refusal now reads as a configuration error with a `change_model` action naming the model handle, instead of "review the prompt, parameters, and inputs", and the HTTP status is unchanged at 500. Correct the existing "A transport error inside a structured-output call is classified again" entry from "1.16 and later" to "1.15.3 and later" (design D5).
- [ ] Add a note to `L-260927-24b43d` saying the lock moved from instructor 1.15.1 to 1.17.0 in `85729dfd3`, since that item's evidence cites 1.15.1 internals and needs re-reading at the new version.
- [ ] Run `make agent-check`, then `make agent-test`.

### Checkpoint

- [ ] Record here the final wording of the advice and anything review changed in the design.
- [ ] Run `/rev`, then open the pull request with `Closes L-260927-086ea4`.

## Out of scope, with where it lives

- Refusing a model the account cannot use at validation: `L-260927-2a587b` (`pipelex-server`). Resolving every model reference to a served handle: `L-260925-cfb6f3`.
- The api-dev gateway's allow-list disagreeing with the remote config: `L-260923-2c7f6b` (`pipelex-remote-config`).
- Usage accounting across re-asked attempts: `L-260927-24b43d`.
