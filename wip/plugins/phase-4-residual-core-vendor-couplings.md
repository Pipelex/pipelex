# Phase 4 — residual core→vendor couplings outside the enumerated seams

Phase 4 inverted the 5th and last *dispatch* seam (`model_lists.py`'s `match sdk:`), so every seam the plan enumerated now names no integration: the four inference worker factories, model listing, orchestrator dispatch, the boot/teardown hub swap, and the CLI (removed in Option A). With those done, "core names no integration" holds **for the dispatch surfaces the effort was scoped to**.

The CHECKPOINT-4 verification grep is broader than those surfaces, though, and it surfaces three **pre-existing** `pipelex.plugins.<vendor>` references in core that were never part of the Phase 0–4 seam list. They are recorded here so the "core names no integration" claim stays precise and a future session can decide their fate. None were introduced by Phase 4 — all three are unchanged from `main`.

## 1. `cogt/config_cogt.py` — vendor config models (by design, not a leak)

```
from pipelex.plugins.anthropic.anthropic_config import AnthropicConfig
from pipelex.plugins.google.google_config import GoogleConfig
from pipelex.plugins.mistral.mistral_config import MistralConfig
from pipelex.plugins.openai.openai_config import OpenAIConfig
```

This is the **typed-config-in-core** pattern, an explicit decision: the design's "Deferred / out of scope" list keeps per-plugin *typed config* in core ("Generic per-plugin typed-config namespace — Temporal config stays typed in core (design D7)"). Inverting it would mean a generic per-plugin config namespace, which the design deliberately declined. **Leave as-is** unless that decision is revisited.

## 2. `cogt/img_gen/img_gen_args_factory.py` — `OpenAIImgGenFactory` (genuine, unscoped)

`ImgGenArgsFactory` imports `OpenAIImgGenFactory` at module top to build provider-specific image-generation API arguments. This is a real core→vendor coupling, but it is an **argument-shaping** concern, not one of the worker-dispatch / listing / orchestrator / boot / config / CLI seams the plan enumerated. Inverting it would need its own capability on the contract (an "img-gen args" SPI), i.e. genuine new design — not a checkpoint cleanup. **Deferred; needs a design decision before it becomes a seam.**

## 3. `cogt/model_backends/backend_factory.py` — `VertexAIFactory` (genuine, unscoped)

```python
match name:
    case "vertexai":
        from pipelex.plugins.openai.vertexai_factory import VertexAIFactory  # noqa: PLC0415
        endpoint, api_key = VertexAIFactory.make_endpoint_and_api_key(extra_config=extra_config)
```

A lazy, `match`-guarded import that resolves vertexai's special endpoint/api-key auth during backend construction. Like (2), a real coupling but a **backend-auth** concern outside the enumerated seams; inverting it would need a backend-auth capability on the contract. **Deferred; needs a design decision before it becomes a seam.**

## Disposition

- (1) is **intentional** per D7 — not a follow-up, just documented so the grep result reads honestly.
- (2) and (3) are **genuine additional seams** the original plan did not enumerate. They do not block CHECKPOINT 4 (whose primary assertion — `model_lists.py` names no integration — holds). If the goal is upgraded from "no integration in the enumerated seams" to a literal "no integration anywhere in core," they are the next two candidates, each requiring its own contract capability.
