"""The composition root's view of the built-in plugins: both layers' halves, welded into one list.

``pipelex.providers`` — the built-in vendor adapters — is a declared runtime-layer package, so it may
not name anything that reaches ``interpreter_hub``, which the two plugins next door do by
construction: their job is to construct interpreter-layer objects (a ``DirectOrchestrator``, a
``DirectBundleValidator``, a ``DirectPipeFuncExecutor``). This package is the interpreter-side home
for them, and it is *allowed* to import downward, so composing the two halves here is legal where
doing it in the runtime adapters' own manifest was the weld that made "the adapters are a runtime
layer" false.

There is still exactly one place that answers "what are the built-in plugins, both layers" — it just
lives in the layer permitted to do the welding. The lists below are what ``Pipelex.setup`` (the
interpreter boot) and the ``pipelex plugins list`` diagnostic pass into ``build_registrar``. The third
caller is the runtime layer's own composition root, ``pipelex/runtime_boot.py``, which calls the same
function but defaults to ``RUNTIME_BUILTIN_PLUGINS`` alone — it may not name this module.
See ``docs/contribute/hub-layering.md``.
"""

from pipelex.interpreter_plugins.direct.direct_plugin import DirectOrchestratorPlugin
from pipelex.interpreter_plugins.pipe_func.pipe_func_plugin import PipeFuncPlugin
from pipelex.plugins.contract import PipelexPlugin
from pipelex.providers.builtins import RUNTIME_BUILTIN_PLUGINS, RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES

# The interpreter-layer half: plugins whose adapters name the method interpreter. Both are
# core-unconditional — in-process execution is required infra.
INTERPRETER_BUILTIN_PLUGINS: list[PipelexPlugin] = [
    DirectOrchestratorPlugin(),
    PipeFuncPlugin(),
]

# Interpreter-layer built-ins core requires unconditionally: ``direct`` owns the DIRECT orchestrator
# (you cannot boot without an in-process execution mode) and ``pipe_func`` owns the built-in PipeFunc
# execution modes (``pipe_func_config.execution_mode`` must resolve to a registered factory or boot
# fails loud — ``direct`` must always be present).
INTERPRETER_CORE_UNCONDITIONAL_PLUGIN_NAMES: frozenset[str] = frozenset({"direct", "pipe_func"})

# The plugins Pipelex ships with — discovered at boot ahead of any external entry-point plugin.
BUILTIN_PLUGINS: list[PipelexPlugin] = [*INTERPRETER_BUILTIN_PLUGINS, *RUNTIME_BUILTIN_PLUGINS]

# Every built-in plugin core requires unconditionally, both layers.
CORE_UNCONDITIONAL_PLUGIN_NAMES: frozenset[str] = INTERPRETER_CORE_UNCONDITIONAL_PLUGIN_NAMES | RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES
