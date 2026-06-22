# `/validate` verdict/fault discrimination: latent subclass parity divergence between the two arms

Status: deferred observation from the `/code-review --fix` of the `TemporalBundleValidator` staged diff (`pipelex-temporal`). **Not a present bug — no code change applied.**

## The two arms discriminate "verdict vs fault" differently

`/validate` produces a verdict-as-value: an invalid bundle's `ValidateBundleError` is *returned* as a structured `ErrorReport` (the invalid arm), while a genuine infra fault *propagates* (a no-verdict 5xx). The two registered bundle validators implement that split with different predicates:

- **Direct (in-process) arm** — `pipelex/pipeline/direct_bundle_validator.py`:

  ```python
  except ValidateBundleError as exc:
      return exc.to_error_report()
  ```

  An `except ValidateBundleError` clause catches `ValidateBundleError` **and any subclass of it**.

- **Temporal (dispatched) arm** — `pipelex_temporal/temporal_bundle_validator.py`:

  ```python
  recovered_report = workflow_error.to_error_report()
  if recovered_report.error_type != ValidateBundleError.__name__:
      raise
  return recovered_report
  ```

  The verdict crosses the worker boundary as a structured `ErrorReport` whose `error_type` is the raised exception's `type(self).__name__` (see `pipelex/base_exceptions.py`, `to_error_report` sets `error_type=type(self).__name__`). The arm recognizes a verdict by **exact string equality** with `"ValidateBundleError"`. A subclass would carry the *subclass* name, so this predicate would **not** match it.

## Why it is not a bug today

The validation cascade in `pipelex/pipeline/validate_bundle.py` always raises the concrete `ValidateBundleError` class itself for every content verdict, and there are **no `ValidateBundleError` subclasses anywhere in the tree** (`grep -rn "class .*(ValidateBundleError)"` is empty). So for every reachable invalid-bundle verdict today, `error_type == "ValidateBundleError"` and both arms agree: return the verdict.

## The latent divergence

If someone later introduces a `ValidateBundleError` subclass and raises it from the validation cascade:

- the **direct arm** would still return it as a verdict (its `except` catches subclasses), but
- the **Temporal arm** would `raise` it as a no-verdict 5xx (its name-equality rejects the subclass name).

Same bundle, same intended verdict, two different HTTP outcomes depending on which orchestrator served the request. That is a cross-backend parity break, of exactly the kind the dispatched-`/validate` design is meant to avoid (both backends must answer identically for the same bundle).

## Why deferred, not fixed

- It is latent: zero subclasses exist, so there is no failing input today.
- The string-equality predicate is forced by the wire boundary — the Temporal arm only has the recovered `ErrorReport` (`error_type` string), not the live exception type, so it *cannot* use `isinstance`/`except` the way the in-process arm does without a richer recovery contract.
- The clean fix is not local to the reviewed file: it would mean teaching the recovery layer to carry a "is-this-a-ValidateBundleError-or-subclass" signal (e.g. an `is_validate_verdict` flag on the recovered report, or a verdict marker class hierarchy the recovery preserves), then having **both** arms branch on that signal — a seam change touching `pipelex` and `pipelex-temporal`, well outside the staged diff.

## If/when a `ValidateBundleError` subclass is introduced

Re-open this. The minimal correct fix is to make verdict-recognition subclass-aware on the wire side — e.g. have `convert_pipelex_errors` / `recover_error_report` stamp a stable "validate verdict" discriminator that does not depend on the exact leaf class name, and have both bundle validators branch on that discriminator instead of on `ValidateBundleError.__name__` (Temporal) / `except ValidateBundleError` (direct). That keeps the two arms provably in lockstep regardless of the concrete exception class.
