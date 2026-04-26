# TODOs

## gpt-image-2 follow-ups (deferred from initial integration)

- Azure deployment for `gpt-image-2`: `model_id = "gpt-image-2-2026-04-21"` currently times out — verify the deployment exists on the Azure resource and that the date suffix matches the actual deployed version.
- `safety_checker` failures on OpenAI direct: the four `nude`-tier tests reject; investigate whether the model needs a different `safety_checker` rule (or whether the test fixtures should skip this tier for gpt-image-2).
- Confirm/refine costs for `gpt-image-2`: currently set to `{ input = 8, output = 30 }` (placeholder modelled on `gpt-image-1.5`); replace with official OpenAI pricing once published.
- Add `gpt-image-2` to the remote Pipelex Gateway config (cannot be done from this repo).
- Optional larger refactor: unify the OpenAI img-gen worker onto `ImgGenArgsFactory.make_args_for_model()` so all rules (not just `background`) are honored consistently with Azure.
- Optional test ergonomics: have `test_img_gen_single_transparent` skip-or-xfail automatically for any model whose rules declare `background = "unavailable"`, so the suite is green on those models without losing coverage on capable ones.
