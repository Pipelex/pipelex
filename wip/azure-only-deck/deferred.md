---
status: active
item: L-260918-941a99
---

# Deferred findings — Azure-only deck

Findings raised during this campaign's reviews that are real but outside its scope. Each says what was seen, why it was not done here, and what doing it would involve.

## Two inference error classes now have no raise site

`LLMSettingsValidationError` (`pipelex/cogt/exceptions.py:251`) lost its only raise site when this campaign deleted `ModelDeck.final_validate` and its `_validate_llm_setting` helper — the dead validator that would have rejected the Azure deck's premium tier. `ImgGenSettingsValidationError` (`:255`) was already in that state before this campaign and has no raise site anywhere in the tree either.

Both are still part of the documented error surface: `docs/errors/llm-settings-validation-error.md` and the generated identity snapshot carry them, and consumers outside this repository branch on `error_type`. Removing a class is therefore a wire change, needing `pipelex-dev generate-error-identity` and `generate-error-pages` and a changelog entry of its own, which is a different piece of work from shipping a deck.

**Verified**: `grep -rn 'LLMSettingsValidationError' --include='*.py'` returns only the class definition; the same for `ImgGenSettingsValidationError`.

**To do it**: decide whether the inference-settings validation these two named is coming back in some form. If it is not, delete both classes, regenerate the error identity and the error pages, and note the removed `error_type` values in the changelog as a breaking change for anyone branching on them.
