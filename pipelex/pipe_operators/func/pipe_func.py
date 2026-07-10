import asyncio
import inspect
from typing import Any, Literal, cast, get_args, get_origin, get_type_hints

from pydantic import field_validator
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, TypedNamedStuffSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry


class PipeFuncOutput(PipeOutput):
    pass


class PipeFunc(PipeOperator[PipeFuncOutput]):
    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @field_validator("function_name", mode="before")
    @classmethod
    def validate_function_name(cls, function_name: str) -> str:
        function = func_registry.get_function(function_name)
        if not function:
            # Check if this function was found but is ineligible (e.g., missing return type)
            ineligible_info = func_registry.get_ineligible_function_info(function_name)
            if ineligible_info:
                msg = f"Function '{function_name}' has @pipe_func() decorator but is not eligible for registration: {ineligible_info.reason}"
            else:
                msg = f"Function '{function_name}' not found in registry"
            raise ValueError(msg)

        return_type = get_type_hints(function).get("return")

        if return_type is None:
            msg = f"Function '{function_name}' has no return type annotation"
            raise ValueError(msg)
        if not issubclass(return_type, StuffContent):
            msg = f"Function '{function_name}' return type {return_type} is not a subclass of StuffContent"
            raise TypeError(msg)
        return function_name

    @override
    def validate_inputs_static(self):
        pass

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        function = func_registry.get_required_function(self.function_name)
        return_type: type[StuffContent] | None = get_type_hints(function).get("return")
        if return_type is None:
            msg = (
                f"PipeFunc '{self.code}' failed to validate output with library: The return type of the function is None. "
                "It should be a subclass of StuffContent."
            )
            raise TypeError(msg)
        if self.output.multiplicity and not issubclass(return_type, ListContent):
            msg = (
                f"PipeFunc '{self.code}' output multiplicity is '{self.output.multiplicity}', but the function '{self.function_name}' "
                f"return type {return_type} is not a subclass of ListContent. The output of your PipeFunc is "
                f"'{self.output.to_bundle_representation()}'. The return type of your function should be a subclass of ListContent."
            )
            raise TypeError(msg)
        if not self.output.multiplicity and issubclass(return_type, ListContent):
            msg = (
                f"PipeFunc '{self.code}' output multiplicity is '{self.output.multiplicity}', but the function '{self.function_name}' "
                f"return type {return_type} is a subclass of ListContent. The output of your PipeFunc is "
                f"'{self.output.concept.concept_ref}{self.output.to_bundle_representation()}' "
                f"when it should be '{self.output.concept.concept_ref}' (no multiplicity)."
            )
            raise TypeError(msg)

        # Validate that the function's return type matches the concept's structure class
        concept_structure_class = get_class_registry().get_class(name=self.output.concept.structure_class_name)
        if concept_structure_class is None:
            msg = (
                f"PipeFunc '{self.code}' failed to validate output with library: "
                f"Concept structure class '{self.output.concept.structure_class_name}' not found in registry."
            )
            raise TypeError(msg)

        # When multiplicity is set (e.g., output = "Expense[]"), the return type should be ListContent[T]
        # where T matches the concept's structure class
        if self.output.multiplicity:
            # We already validated that return_type is a subclass of ListContent above.
            # Now check that the generic parameter matches the concept's structure class.
            type_args: tuple[type, ...] | None = None

            # Try standard typing module first
            origin = get_origin(return_type)
            if origin is not None:
                type_args = get_args(return_type)
            else:
                # For Pydantic generics (e.g., ListContent[MyItem]), use Pydantic's metadata
                return_type_for_metadata = cast("type", return_type)
                pydantic_metadata: dict[str, tuple[type, ...]] | None = getattr(return_type_for_metadata, "__pydantic_generic_metadata__", None)
                if pydantic_metadata is not None:
                    type_args = pydantic_metadata.get("args")

            if type_args:
                item_type = type_args[0]
                # Check if item type matches the concept's structure class:
                # 1. Same class object
                # 2. Subclass relationship
                # 3. Same class name (for cases where the class is defined in different modules but represents the same concept)
                is_same_class = item_type == concept_structure_class
                is_subclass = not is_same_class and issubclass(item_type, concept_structure_class)
                is_same_name = item_type.__name__ == self.output.concept.structure_class_name

                # Debug logging
                log.verbose(
                    f"PipeFunc '{self.code}' ListContent validation: "
                    f"item_type={item_type.__module__}.{item_type.__name__}, "
                    f"concept_structure_class={concept_structure_class.__module__}.{concept_structure_class.__name__}, "
                    f"is_same_class={is_same_class}, is_subclass={is_subclass}, is_same_name={is_same_name}"
                )

                if not (is_same_class or is_subclass or is_same_name):
                    msg = (
                        f"PipeFunc '{self.code}' output concept expects structure class '{self.output.concept.structure_class_name}' "
                        f"(from {concept_structure_class.__module__}.{concept_structure_class.__name__}), "
                        f"but the function '{self.function_name}' return type is 'ListContent[{item_type.__name__}]' "
                        f"(from {item_type.__module__}.{item_type.__name__}). "
                        f"The item type of your ListContent should be '{self.output.concept.structure_class_name}' or a subclass of it."
                    )
                    raise TypeError(msg)
            # If no type_args found, return_type is raw ListContent without generic parameter - we already validated it's a ListContent subclass
        else:
            # No multiplicity - return type must match the concept's structure class
            # Same checks as above: same class, subclass, or same name
            is_same_class = return_type == concept_structure_class
            is_subclass = not is_same_class and issubclass(return_type, concept_structure_class)
            is_same_name = return_type.__name__ == self.output.concept.structure_class_name

            if not (is_same_class or is_subclass or is_same_name):
                msg = (
                    f"PipeFunc '{self.code}' output concept expects structure class '{self.output.concept.structure_class_name}', "
                    f"but the function '{self.function_name}' return type is '{return_type.__name__}'. "
                    f"The return type of your function should be '{self.output.concept.structure_class_name}' or a subclass of it."
                )
                raise TypeError(msg)

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeFuncOutput:
        log.verbose(f"Running PipeFunc with function '{self.function_name}'")
        function = func_registry.get_required_function(self.function_name)

        try:
            if inspect.iscoroutinefunction(function):
                func_output_object = await function(working_memory=working_memory)
            else:
                func_output_object = await asyncio.to_thread(function, working_memory=working_memory)
        except Exception as exc:
            # PipeFunc invokes an arbitrary user-registered function whose failure surface is not enumerable;
            # any failure is wrapped into a diagnostic PipeRunError below. Re-raises, never swallows.
            # Build informative error message with actual input values from working memory
            inputs_lines: list[str] = []
            for input_name in self.inputs.root:
                try:
                    stuff = working_memory.get_stuff(name=input_name)
                    inputs_lines.append(f"    {input_name} = {stuff.content!r}")
                except WorkingMemoryStuffNotFoundError:
                    inputs_lines.append(f"    {input_name} = <not found in working memory>")

            inputs_desc = "\n".join(inputs_lines) if inputs_lines else "    none"
            output_desc = self.output.to_bundle_representation()
            msg = (
                f"PipeFunc '{self.code}' failed during execution.\n"
                f"  Expected output: {output_desc}\n"
                f"  Inputs:\n{inputs_desc}\n\n"
                f"  Error: {type(exc).__name__}: {exc}"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        the_content: StuffContent
        if isinstance(func_output_object, StuffContent):
            the_content = func_output_object
        elif isinstance(func_output_object, list):
            func_result_list = cast("list[StuffContent]", func_output_object)
            the_content = ListContent(items=func_result_list)
        elif isinstance(func_output_object, str):
            the_content = TextContent(text=func_output_object)
        else:
            msg = f"Function '{self.function_name}' must return a StuffContent or a list, got {type(func_output_object)}"
            raise TypeError(msg)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        # Capture execution data for the graph tracer. PipeFunc has no prompts or
        # models to record, but the sidepanel should still show *what* function ran
        # and what kind of content it returned — useful for debugging and for
        # distinguishing multiple PipeFunc nodes in a graph.
        execution_data_dict: dict[str, Any] = {
            "function_name": self.function_name,
            "function_module": getattr(function, "__module__", None),
            "function_qualname": getattr(function, "__qualname__", self.function_name),
            "output_content_type": type(the_content).__name__,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeFuncOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeFuncOutput:
        function = func_registry.get_required_function(self.function_name)
        log.info(
            f"🚨 For your information, the dry run of PipeFunc '{self.code}' is not actually running the python function \
            but only validating the inputs and return type."
        )
        return_type = get_type_hints(function).get("return")
        if return_type is None:
            msg = f"Dry run of {self.type} '{self.code}' failed: The return type of the function is None. It should be a subclass of StuffContent."
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

        # TODO: Support PipeFunc returning with multiplicity. Create an equivalent of TypedNamedInputRequirement for outputs.
        stuff_spec = TypedNamedStuffSpec(
            variable_name="mock_output",
            concept=ConceptFactory.make(
                concept_code=self.output.concept.code,
                domain_code="generic",
                description="Lorem Ipsum",
                structure_class_name=self.output.concept.structure_class_name,
            ),
            structure_class=return_type,
            multiplicity=False,
        )
        mock_content = WorkingMemoryFactory.make_mock_content(stuff_spec)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
            content=mock_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        # Capture execution data for the graph tracer. Dry run does NOT invoke the
        # real function — we flag that explicitly so the sidepanel can show a
        # "mock output" indicator and explain why no real function_result is present.
        execution_data_dict: dict[str, Any] = {
            "function_name": self.function_name,
            "function_module": getattr(function, "__module__", None),
            "function_qualname": getattr(function, "__qualname__", self.function_name),
            "output_content_type": type(mock_content).__name__,
            "is_mock_output": True,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeFuncOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        function = func_registry.get_required_function(self.function_name)
        return_type = get_type_hints(function).get("return")
        # TODO: this should not happend ever. The correct way to do this would be to have a unit test making sure
        # that the FuncRegistry DOES CALL the 'is_eligible_function' function, and this function should be unit tested.
        if return_type is None:
            msg = f"Dry run failed for {self.type} '{self.code}': function '{self.function_name}' has no return type annotation"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
        if not issubclass(return_type, StuffContent):
            msg = (
                f"Dry run failed for pipe {self.type} '{self.code}': "
                f"function '{self.function_name}' return type {return_type} is not a subclass of StuffContent"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
