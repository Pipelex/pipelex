from enum import StrEnum


class PluginGroup(StrEnum):
    """The entry-point group a plugin publishes under — and therefore the layer it declares.

    ``[project.entry-points."pipelex.plugins.kernel"]`` for a plugin whose adapters are all
    kernel-layer, ``[project.entry-points."pipelex.plugins.interpreter"]`` for one that constructs
    any ``Pipe``-aware object. The group is not documentation: a kernel-only boot asks the
    installed-distribution metadata for the kernel group *alone*, so an interpreter-group plugin's
    module is never even imported there — which is the whole point, since importing it is what drags
    the method interpreter into the process.

    Its own module rather than ``contract.py`` only because the registrar needs it at runtime (it is
    a ``PluginDiscovery`` field) while ``contract.py`` names the registrar back.
    """

    KERNEL = "pipelex.plugins.kernel"
    INTERPRETER = "pipelex.plugins.interpreter"

    @property
    def is_kernel(self) -> bool:
        match self:
            case PluginGroup.KERNEL:
                return True
            case PluginGroup.INTERPRETER:
                return False
