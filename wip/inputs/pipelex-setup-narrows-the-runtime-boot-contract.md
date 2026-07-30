# `Pipelex.setup` narrows its base class's parameter list, and `**kwargs` turns that into a runtime error

**Status:** deferred as a design tradeoff, not applied. Found by an adversarial review pass on PR #1073. Nothing in the workspace hits it; the honest fix is a signature decision rather than a patch.

## What happens

`RuntimeBoot.setup()` documents `builtin_plugins` and `core_unconditional_plugin_names` as part of its contract — they are how a runtime-only boot discovers exactly the runtime half of the built-in plugins. `Pipelex.setup()` is an `@override` that deliberately does *not* accept them, because it supplies its own composed manifests (`BUILTIN_PLUGINS`, `CORE_UNCONDITIONAL_PLUGIN_NAMES`) to `super().setup()`.

It absorbs the difference in `**kwargs: Any` and rejects it:

```python
if kwargs:
    msg = f"The Pipelex setup method does not support any additional arguments: {kwargs}"
    raise PipelexSetupError(msg)
```

So `pipelex_instance.setup(integration_mode=…, builtin_plugins=[])` type-checks — `**kwargs: Any` swallows the argument, and pyright sees nothing wrong — and raises at run time. A caller who wrote against the *base* type gets a green type check and a failure in production.

## Why it was not "fixed"

Every candidate remedy trades one wart for another, and the current behaviour is not the worst of them:

- **Accept and ignore them.** Silently discarding a caller's plugin manifests is worse than refusing: they asked for a specific plugin set and would get a different one with no signal.
- **Accept and honour them.** That contradicts what `Pipelex` *is* — the boot that runs methods, and therefore needs the interpreter-touching built-ins. A caller who wants a different set wants `RuntimeBoot`.
- **Drop `**kwargs` and let Python raise `TypeError`.** Arguably the most honest, and it makes the narrowing visible to pyright at the call site. But `**kwargs` is doing a second job here — catching typo'd keyword arguments across a 17-parameter surface with a message that names them — and the `TypeError` wording would be worse for the common case.
- **Split the base signature** so the manifest parameters live on a separate protected method the subclass overrides instead of on `setup()`. This is the actually-correct answer, and it is a change to a public injection contract that does not belong in a placement refactor.

The narrowing is real (`Pipelex.setup` is not substitutable for `RuntimeBoot.setup`), and it is at least *loud* — the failure names the offending argument. Worth revisiting alongside any other work on the `setup()` signature; not worth a workaround on its own.

## What exists today instead

Nothing in the workspace passes either parameter to `Pipelex.setup`, and `Pipelex.make()` — the way essentially every consumer boots — does not expose them at all, so the reachable surface is a direct `setup()` call on a constructed instance.
