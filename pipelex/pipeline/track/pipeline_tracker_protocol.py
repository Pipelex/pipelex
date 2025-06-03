# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeArgument=false
from typing import List, Optional, Protocol

from typing_extensions import override

from pipelex.core.stuff import Stuff
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionDetails


class PipelineTrackerProtocol(Protocol):
    def setup(self): ...

    def teardown(self): ...

    # def reset(self): ...
    def add_pipe_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        pipe_code: str,
        comment: str,
        pipe_layer: List[str],
        as_item_index: Optional[int] = None,
        is_with_edge: bool = True,
    ): ...

    def add_batch_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        to_branch_index: int,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def add_aggregate_step(
        self,
        from_stuff: Stuff,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def add_condition_step(
        self,
        from_stuff: Stuff,
        to_condition: PipeConditionDetails,
        condition_expression: str,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def add_choice_step(
        self,
        from_condition: PipeConditionDetails,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ): ...

    def output_flowchart(
        self,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        is_detailed: bool = False,
    ): ...


class PipelineTrackerNoOp(PipelineTrackerProtocol):
    """A no-operation implementation of PipelineTrackerProtocol that does nothing.
    This is useful when pipeline tracking needs to be disabled.
    """

    @override
    def setup(self) -> None:
        pass

    @override
    def teardown(self) -> None:
        pass

    @override
    def add_pipe_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        pipe_code: str,
        comment: str,
        pipe_layer: List[str],
        as_item_index: Optional[int] = None,
        is_with_edge: bool = True,
    ) -> None:
        pass

    @override
    def add_batch_step(
        self,
        from_stuff: Optional[Stuff],
        to_stuff: Stuff,
        to_branch_index: int,
        pipe_layer: List[str],
        comment: str,
    ) -> None:
        pass

    @override
    def add_aggregate_step(
        self,
        from_stuff: Stuff,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ) -> None:
        pass

    @override
    def add_condition_step(
        self,
        from_stuff: Stuff,
        to_condition: PipeConditionDetails,
        condition_expression: str,
        pipe_layer: List[str],
        comment: str,
    ) -> None:
        pass

    @override
    def add_choice_step(
        self,
        from_condition: PipeConditionDetails,
        to_stuff: Stuff,
        pipe_layer: List[str],
        comment: str,
    ) -> None:
        pass

    @override
    def output_flowchart(
        self,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        is_detailed: bool = False,
    ) -> None:
        pass
