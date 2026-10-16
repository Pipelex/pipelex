"""The seam through which a deployment states the Python packages its PipeFunc steps run with, out of this process.

A method declares the packages its Python needs in the `requirements.txt` at the root of its method tree, and pipelex
checks them when the method loads (`pipelex/libraries/method_requirements.py`). In the `direct` execution mode a
PipeFunc runs in this interpreter, so the check reads this interpreter's installed distributions. In any other mode it
runs in a sandbox this process never sees, such as the Daytona sandbox, whose packages are the whole offer: pipelex
cannot read them, so the plugin that contributes the mode's executor states them here, with
``PluginRegistrar.add_pipe_func_package_offer``, keyed by the same execution mode token.

A mode for which no plugin states a package set, or whose factory answers ``None``, meets no requirement at all: the
check fails closed rather than letting a method load whose Python would then fail inside the sandbox.
"""

from collections.abc import Callable, Mapping
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from pipelex.system.configuration.pipe_func_config import PipeFuncConfig


class PipeFuncPackageOffer(BaseModel):
    """The Python packages a PipeFunc step finds where an execution mode runs it, and the marker environment there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: str = Field(
        description=(
            "The place the packages are offered, as a refusal names it to the method's author, such as "
            "\"the Daytona sandbox snapshot 'pipelex-base-dev'\"."
        )
    )
    distributions: dict[str, str] = Field(
        description="Each distribution the place holds, by its name (normalized or not), with its exact installed version."
    )
    marker_environment: dict[str, str] = Field(
        description=(
            "The PEP 508 environment marker values of the place's interpreter, such as python_version and sys_platform. "
            "A requirement whose marker reads a variable missing here cannot be judged, and is refused."
        )
    )


# A plugin's factory for the package offer of one PipeFunc execution mode: the pipe_func config in, the offer out, or
# ``None`` when the deployment cannot state it. Called each time a method declaring requirements loads, never at
# registration, so a factory may read its own configuration and should cache what it computes.
PipeFuncPackageOfferFactoryFn: TypeAlias = Callable[[PipeFuncConfig], PipeFuncPackageOffer | None]


class PipeFuncPackageOfferRegistry:
    """Read view over the package-offer factories contributed by discovered plugins, keyed by execution mode.

    Built once at boot from the registrar's accumulated ``pipe_func_package_offers`` and stored on the interpreter hub,
    beside the ``PipeFuncExecutorRegistry`` whose modes it mirrors. The ``direct`` mode needs no entry: its packages
    are this interpreter's own.
    """

    def __init__(self, pipe_func_package_offers: Mapping[str, PipeFuncPackageOfferFactoryFn]):
        self._pipe_func_package_offers: dict[str, PipeFuncPackageOfferFactoryFn] = dict(pipe_func_package_offers)

    def get_optional(self, *, mode: str) -> PipeFuncPackageOfferFactoryFn | None:
        return self._pipe_func_package_offers.get(mode)

    @property
    def modes(self) -> list[str]:
        return list(self._pipe_func_package_offers)
