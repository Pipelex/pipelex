# Portable image size for image generation — design

Supersedes `wip/gemini-img-gen-size-tier-follow-up.md` (Gemini-only follow-up note, now folded in here). Deferred from the Gemini 3.1 aspect-ratio work on `feature/Img2Img-with-gpt-image`.

## The promise

Pipelex abstracts away provider APIs. For image size that means: a `PipeImgGen` in a bundle carries a size intent, and switching the pipe's `model` between providers (Google ↔ OpenAI ↔ anything else) **adapts when the intent is satisfiable and raises a validation error when it is not** — in both directions, ideally at blueprint-load time. We face the future: the newest models (Gemini 3.x size tiers up to 4K, gpt-image-2 arbitrary exact sizes) get first-class access even where older models can't follow.

## Provider landscape

The two flagship providers speak opposite size dialects, and the older models barely speak at all:

| Model family | Size control | Values / constraints |
| --- | --- | --- |
| Gemini 2.5 Flash Image (nano-banana) | none | 1K fixed, standard ratios |
| Gemini 3 Pro Image (nano-banana-pro) | tier | `1K`/`2K`/`4K`, standard ratios only |
| Gemini 3.1 Flash Image (nano-banana-2) | tier | `1K`/`2K`/`4K` + published 512px grid (wire token unconfirmed), all ratios incl. banners |
| Gemini 3.1 Flash Lite Image | none | 1K fixed |
| OpenAI gpt-image-1 / -1-mini / -1.5 (legacy) | fixed sizes | `1024x1024`, `1536x1024`, `1024x1536` |
| OpenAI gpt-image-2 | arbitrary exact WxH | multiples of 16, max edge < 3840, long:short ≤ 3:1, 0.65–8.29 MP, reliability boundary 2560×1440 |
| Flux / Flux 1.1 Ultra / SDXL / Qwen (fal) | none | aspect-ratio presets only, ~1–1.6 MP outputs |

Key facts about current code:

- `ImgGenJobParams.size` is an `ImageSize` (exact width/height) that **nothing populates** — a dead wire aimed at the OpenAI exact-size path. `OpenAIImgGenFactory.size_for_gpt_image_2` + `validate_gpt_image_2_size` already implement the real gpt-image-2 constraints.
- The Google worker **hardcodes `size="1K"`** and never sends `image_size` on the wire; `GoogleImgGenFactory` already holds the full Gemini 3 grids at 1K/2K/4K, unreachable in production. The gateway path is the same (`# "image_size": "2K"` commented out in `gateway_factory.py`).
- Google image models have **no `rules` block in the deck**, so `PipeImgGen._validate_param_support_against_model_rules` silently skips them — an unsupported aspect ratio on nano-banana today only fails at runtime. OpenAI models do have rules and get static validation.
- The installed google-genai SDK types `ImageConfig.image_size` as open `str` documented as `1K`/`2K`/`4K`; the 512px column Google publishes for Gemini 3.1 Flash has no confirmed wire token yet.

## Design decisions (settled with Louis, 2026-07-02)

1. **One `size` field** on the pipe, accepting either a portable **tier token** or an **exact `WxH`** — not two separate fields, not tier-only.
2. **Exact-grid match** when an exact size hits a tier-grid model: if the WxH exactly equals a cell of the model's published grid, derive (aspect ratio, tier) and run; otherwise validation error naming the nearest valid cells. Never silently snap.
3. **`1k` is satisfiable everywhere** a model natively produces ~1K-class images (Flux, SDXL, Qwen, legacy gpt-image, nano-banana, lite) — accepted as a no-op. Unsatisfiable tiers (`2k` on Flux, `4k` on gpt-image-2, `0.5k` anywhere but Gemini 3.1 Flash) are **hard validation errors**, never warn-and-ignore.
4. **Google per-model gating moves into deck rules** (in scope): Google image models get `rules` blocks and a Google geometry taxonomy, closing the static-validation gap so model switching is checked at load time in both directions.

## The `size` field

```toml
[pipe.render_poster]
type = "PipeImgGen"
prompt = "..."
model = "nano-banana-2"
aspect_ratio = "landscape_16_9"
size = "2k"            # portable tier: "0.5k" | "1k" | "2k" | "4k"

# expert mode — exact pixels (gpt-image-2-class models):
# size = "2048x1152"   # aspect_ratio is then forbidden: the size implies it
```

**Semantics of a tier**: "produce this pixel class at my chosen `aspect_ratio`". A tier promises a class, **not identical pixel dimensions across providers** — `size = "2k"` at 16:9 yields 2752×1536 on nano-banana-2 (Google's grid) and 3072×1728 on gpt-image-2 (our computed table). Both are 2K-class; that is the abstraction.

**Semantics of an exact size**: "produce exactly these pixels". Deterministic everywhere it runs; models that cannot hit the exact dims reject at validation.

**Interaction with `aspect_ratio`**: a tier composes with `aspect_ratio` (which keeps its current default behavior). An exact size *implies* a ratio, so setting both `size = "WxH"` and `aspect_ratio` is a blueprint validation error — no silent precedence.

### Types and parsing

- New `SizeTier` StrEnum in `img_gen_job_components.py`, next to `AspectRatio`: `HALF_K = "0.5k"`, `ONE_K = "1k"`, `TWO_K = "2k"`, `FOUR_K = "4k"`.
- `ImgGenJobParams.size` becomes `SizeTier | ImageSize | None` with a `BeforeValidator` that parses strings: a tier token → `SizeTier`, `"<int>x<int>"` → `ImageSize`, anything else → clear `ValueError`. Both arms serialize cleanly (StrEnum as str, `ImageSize` as dict), so the union is wire-safe.
- `PipeImgGenBlueprint.size` / `PipeImgGenSpec.size` use the same annotated union, so the MTHDS JSON Schema exposes enum-or-pattern for editors. Blueprint gains the `size`-vs-`aspect_ratio` exclusivity validator.
- `PipeImgGen` threads `self.size or img_gen_param_defaults.size` into `ImgGenJobParams` like the other one-time settings.
- `ImgGenJobParamsDefaults` gains optional `size` (class default `None` per config rules — `None` means "provider default", no key added to `pipelex.toml` or `.pipelex/pipelex.toml`). `ImgGenSetting` (deck presets) deliberately does **not** get `size`: geometry is pipe intent, not model preset — revisit only if a real "4k-img-gen preset" need materializes.

## Per-provider mapping

### Google Gemini (native worker + gateway)

- Tier → `image_config.image_size` wire token (`"1k"` → `"1K"`, etc.). **Omit the param when `size` is unset** so the provider default (1K) applies — never silently upgrade, since 2K/4K cost proportionally more output tokens.
- The worker stops hardcoding `"1K"`; computed grid dims keep stamping `GeneratedImageRawDetails.size` metadata as today.
- Exact size → **exact-grid match**: search the model's grids for a cell equal to WxH; on hit, derive (ratio, tier) and proceed exactly as if the user had written them; on miss, `ImgGenParameterError` suggesting the nearest cells (same or adjacent ratio, closest area). So a bundle written for gpt-image-2 with `size = "2048x2048"` runs on nano-banana-2 (1:1 @ 2K), while `"2000x2000"` errors with "did you mean 2048x2048 (square @ 2k)?".
- Per-model gating (which tiers, which ratios) moves out of the `GoogleImageGenModel` name-enum `match` in `GoogleImgGenFactory` and into deck rules (below). The dimension grids stay in the factory as the single source of truth for dims.
- `gateway_factory.make_extras` threads the same `image_size` into `extra_body["image_config"]` for gemini-routed jobs.
- **0.5k tier**: grid dims are published (1:1 512×512, 1:4 256×1024, 1:8 192×1536, 2:3 424×632, 3:2 632×424, 3:4 448×600, 4:1 1024×256, 4:3 600×448, 4:5 464×576, 5:4 576×464, 8:1 1536×192, 9:16 384×688, 16:9 688×384, 21:9 792×168) but the wire token is unverified — the SDK documents only `1K`/`2K`/`4K` while the field is open `str`. Ship `1k`/`2k`/`4k` first; `0.5k` lands behind an empirical wire test against Gemini 3.1 Flash (try `"512"` / `"0.5K"`; if neither works, `0.5k` stays a validation error on every model until Google opens it).

### OpenAI gpt-image-2

- Tier → computed exact size by **scaling the existing 1K preset table** (`GPT_IMAGE_2_ASPECT_RATIO_TO_SIZE`): `2k` = ×2 per edge, `0.5k` = ×½, `4k` = ×4, then run the result through the existing `validate_gpt_image_2_size`. Verified outcomes:
  - `2k`: every supported ratio stays valid (all cells remain multiples of 16, max edge 3584 < 3840, max 7.08 MP < 8.29 MP). All 2K cells sit above the 2560×1440 reliability boundary, so the existing warning fires — keep it (it reflects OpenAI's documented boundary) but demote to `log.verbose` for tier-derived sizes, reserving the loud warning for user-supplied exact sizes.
  - `4k`: every ratio violates max edge and/or pixel cap → validation error ("gpt-image-2 caps out below 4K; use 2k or an exact size ≤ 8.29 MP").
  - `0.5k`: every ratio falls below the 0.65 MP floor → validation error.
  - Rejected alternative: computing dims from a constant pixel budget per tier (closer to Google's constant-area semantics). Doubling wins on simplicity, keeps the shipped 1K presets as the anchor, and produces OpenAI-round numbers; the class overshoot on wide ratios is acceptable because a tier is a class, not a dims contract.
- Exact size → existing pass-through + validation, unchanged.

### Legacy gpt-image (gpt-image-1 / -1-mini / -1.5)

- Tier `1k` → the existing fixed size for the chosen ratio (that grid *is* the 1K class); `0.5k`/`2k`/`4k` → validation error.
- Exact size → existing behavior (only the fixed sizes accepted).

### Flux / Flux 1.1 Ultra / SDXL / Qwen

- Tier `1k` → accepted as a no-op (their native outputs are 1K-class); `0.5k`/`2k`/`4k` → validation error.
- Exact size → validation error ("this model does not support exact sizes; use aspect_ratio, optionally with size = '1k'").

## Rules, taxonomy, and validation

Aspect ratio and size are one entangled concern per provider (one `size` param on OpenAI, one `image_config` on Google, one grid lookup for dims), and the code already reflects it: `make_args_from_aspect_ratio` takes `size`, and `ImgGenParamSupport.check_aspect_ratio` reuses it. The design leans into that:

- **Keep the topic named `aspect_ratio`** (no rename). The key appears in the `[model.rules]` blocks of backend TOMLs — a user-writable config surface (custom model registration, the add-model workflow), and that vocabulary should match what users know from blueprints (`aspect_ratio`, `size`), not introduce a third word. The topic's joint responsibility for ratio + size is documented in the `AspectRatioTaxonomy` docstring; `make_args_from_aspect_ratio` and `check_aspect_ratio` already take `size`, so no code rename is needed either. (Rejected alternative: `ImgGenArgTopic.ASPECT_RATIO` → `GEOMETRY` across code + deck TOMLs — internal naming purity wasn't worth config-vocabulary drift on a user-facing surface.)
- **New Google taxonomy values**, one per capability generation: `gemini_2_5` (1K only, standard ratios), `gemini_3_pro` (1K/2K/4K, standard ratios), `gemini_3_flash` (all tiers incl. 0.5k-when-verified, all ratios), `gemini_3_flash_lite` (1K only, all ratios). Each value encodes its (ratio set × tier set); `GoogleImgGenFactory` is re-keyed by taxonomy instead of matching on model *names*, killing the fragile `GoogleImageGenModel` enum (model handles are deck config, not code constants).
- **Deck**: `google.toml` image models gain `rules` blocks (at minimum `aspect_ratio = "gemini_3_flash"` etc.). This is what turns on static blueprint validation for Google — today `spec.rules is None` short-circuits it.
- **`ImgGenParamSupport`**: `check_aspect_ratio` covers (aspect_ratio, size) jointly — it already receives `size`, now including tier values; `check_blueprint_params` now receives the explicitly-set `size` (today it passes `size=None`), and `check_job_params` picks it from params as before. The existing unknown-taxonomy abstain policy stays (gateway rules may predate the enum).
- **Failure timing**: when the pipe's model choice resolves to a concrete spec with rules → error at blueprint-load time; when the choice is a preset/alias resolved later → same check errors at runtime before any API call. Same two-layer pattern the aspect-ratio work shipped.

## Portability worked examples (the acceptance bar)

- `nano-banana-2` + `aspect_ratio = "landscape_16_9"` + `size = "2k"` → switch model to `gpt-image-2`: runs, 2K-class dims (3072×1728). Switch to `flux-pro/v1.1`: **load-time error** ("flux cannot produce 2k; supported: 1k").
- `gpt-image-2` + `size = "2048x2048"` → switch to `nano-banana-2`: runs (1:1 @ 2K exact-grid hit). With `size = "2000x2000"`: **error** suggesting 2048x2048.
- `fast-img-gen` (SDXL) + `size = "1k"` → switch to any model: runs everywhere (worst case as a no-op); only `0.5k`-capable check would block it nowhere.
- `nano-banana-2` + `size = "4k"` → switch to `gpt-image-2`: **error** (above its pixel cap) — honest refusal, not a silent downgrade.

## Cost note

Tiers change the bill: Google output tokens scale with tier (4K ≫ 1K), OpenAI prices scale with size. Usage reporting needs no code change (token usage comes from responses), but the `PipeImgGen` docs must state that `2k`/`4k` cost proportionally more, and the never-send-unless-set rule above keeps unset bundles at provider-default cost.

## Implementation plan

### Phase 1 — types & surface

`SizeTier` + union parsing on `ImgGenJobParams.size`; blueprint/spec `size` field + `aspect_ratio` exclusivity validator; threading in `PipeImgGen`; optional default in `ImgGenJobParamsDefaults`. TDD: parsing unit tests (tier / exact / garbage), blueprint validator tests.

### Phase 2 — rules & validation

Google taxonomy values on `AspectRatioTaxonomy` (+ docstring stating the topic governs ratio and size jointly); `google.toml` rules blocks; `GoogleImgGenFactory` re-keyed by taxonomy (grids unchanged); `ImgGenParamSupport.check_aspect_ratio` extended for tiers incl. blueprint-side `size`; exact-grid match + nearest-cell error messages. TDD: per-taxonomy support matrices, exact-grid hit/miss, static-validation tests for Google models (the previously-skipped gap).

**CHECKPOINT** — validation story complete and green before any wire change; natural handoff point (Phase 3 opens the worker/API-call area).

### Phase 3 — wire

Google worker sends `image_size` (omit when unset), stops hardcoding `"1K"`; gateway `make_extras` threads the same; `ImgGenArgsFactory` handles the union for OpenAI paths (tier → scaled table → existing validator, verbose-not-warning for tier-derived reliability overshoot); metadata dims stamping for tiers.

### Phase 4 — docs, e2e & release

`PipeImgGen.md` param table + portability section with the worked examples; cogt-config docs; MTHDS schema regen; changelog. E2E smoke: one 2K gen on nano-banana-2 and one on gpt-image-2 (cost-gated test profile).

### Follow-up (separate)

- `0.5k` wire-token verification against Gemini 3.1 Flash, then enable in `gemini_3_flash` taxonomy + add the 512px grid to the factory.
- `AspectRatio` enum lacks 4:5/5:4, which the Gemini grids publish — decide separately whether to add them.
