"""The seam through which a deployment states the Python packages its PipeFunc steps run with, out of this process.

A method declares the packages its Python needs in the `requirements.txt` at the root of its method tree, and pipelex
checks them when the method loads (`pipelex/libraries/method_requirements.py`). In the `direct` execution mode a
PipeFunc runs in this interpreter, so the check reads this interpreter's installed distributions. In any other mode it
runs in a sandbox this process never sees, such as the Daytona sandbox, whose packages are the whole offer: pipelex
cannot read them, so the plugin that contributes the mode's executor states them here, with
``PluginRegistrar.add_pipe_func_package_offer``, keyed by the same execution mode token.

The factory is asked for one method's requirements at a time, so a mode whose sandbox is not one fixed package set, such
as one building an environment for each method, states the environment it would run that method in, or refuses the
requirements with its own reason when no environment it can build holds them.

A mode for which no plugin states a package set, or whose factory answers ``None``, meets no requirement at all: the
check fails closed rather than letting a method load whose Python would then fail inside the sandbox.
"""

from collections.abc import Callable, Mapping
from typing import NamedTuple, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.method_trees.requirements_file import RequirementLine
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


class PipeFuncPackageRefusal(BaseModel):
    """An execution mode's answer that no environment it can run a PipeFunc step in holds the requirements it was asked for.

    The method declaring them is refused when it loads, as an input fault of the method's: its error carries the
    reason, so the reason names no path on the host, since it reaches the method's author, a server's caller included.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: str = Field(
        description="The place the packages would be offered, as the refusal names it to the method's author, such as 'the Daytona sandbox'."
    )
    reason: str = Field(
        description=(
            "Why no environment of the place holds the requirements, in the plugin's own words, such as a resolver's "
            "explanation of the conflict it found."
        )
    )


class PipeFuncPackageOfferRequest(NamedTuple):
    """What a package-offer factory is asked: the packages it offers for one method's requirements.

    ``requirements`` are every requirement the method's `requirements.txt` declares, in the file's order, markers
    included, as the MTHDS standard reads them: the factory answers for them all, and pipelex then judges each against
    the offer, a requirement whose marker is false there included.
    """

    pipe_func_config: PipeFuncConfig
    requirements: tuple[RequirementLine, ...]


# A plugin's factory for the package offer of one PipeFunc execution mode: the request in; out, the offer meeting the
# requirements it names (the mode's fixed package set, or an environment built for them), a refusal carrying the
# plugin's reason when no environment of the mode can hold them, or ``None`` when the deployment cannot state its
# packages at all. Called synchronously, once for each method tree declaring requirements each time a check judges it,
# never at registration, from whatever thread runs the load, which may be running an event loop. It is therefore
# synchronous, and caching its answers by the requirements is the plugin's job: a factory whose answer takes time to
# compute, such as one resolving the requirements with a resolver, bounds the work with a timeout of its own and caches
# by the requirements' texts, so only a process's first check of a requirement set pays for it. A fault of its own,
# such as a resolver it cannot reach, is raised as an error of the plugin's, never answered as a refusal.
PipeFuncPackageOfferFactoryFn: TypeAlias = Callable[[PipeFuncPackageOfferRequest], PipeFuncPackageOffer | PipeFuncPackageRefusal | None]


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
