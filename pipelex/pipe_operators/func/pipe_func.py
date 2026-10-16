from collections.abc import Callable
from contextlib import nullcontext
from typing import Any, Literal, cast, get_args, get_origin, get_type_hints

from mthds.method_tree.tree_path import nfc
from pydantic import PrivateAttr, field_validator
from typing_extensions import override

from pipelex import log
from pipelex.config import is_pipe_func_sandbox_hosted
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.exceptions import TreePythonError
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.core.method_trees.tree_python import check_tree_module_names, top_level_module_names, tree_label_holding
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, TypedNamedStuffSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_current_library_id_or_none, get_library_manager, get_pipe_func_executor
from pipelex.kernel.memory_ops import store_result
from pipelex.libraries.library_crate import SUBMITTED_PYTHON_ROOT_KEY
from pipelex.pipe_operators.func.exceptions import PipeFuncFunctionError
from pipelex.pipe_operators.func.function_name import function_name_form_violation
from pipelex.pipe_operators.func.pipe_func_call_context import pipe_func_call_in_flight
from pipelex.pipe_operators.func.pipe_func_python import (
    PipeFuncModuleSource,
    bind_import_path_function,
    bind_tree_function,
    check_pipe_func_definition,
    locate_in_files,
    locate_in_tree,
    locate_on_import_path,
)
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_hub import get_class_registry
from pipelex.system.job_metadata import JobMetadata
from pipelex.validation_error_types import PipeValidationErrorType

#: Who holds a tree's Python for a run with no current library, such as a pipe run directly by a test.
_PROCESS_HOLDER = "process"


class PipeFuncOutput(PipeOutput):
    pass


class PipeFunc(PipeOperator[PipeFuncOutput]):
    """Calls a Python function the step names by import path from the root of its method tree.

    The function is located and its form proven at validation, without running Python; it is imported, and its calling
    convention and return type checked, when the step first runs, dry or live. In `direct` mode it is imported in
    this process, under the process's hold on the tree's Python; in a sandbox-hosted mode it never is, and the call
    travels to the sandbox with the tree's files. See `pipe_func_python` for where a `function_name` resolves.
    """

    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str

    # The member of its method tree the step's bundle was read as, which the function's import path resolves in; None
    # for a bundle parsed from a content string. Set by the factory, never serialized: a pipe is rebuilt from its
    # blueprint wherever it travels, and the crate carries the tree.
    _tree_bundle: TreeBundle | None = PrivateAttr(default=None)
    # The function once imported and checked, with the holder its import was made for.
    _bound_function: tuple[str, Callable[..., Any]] | None = PrivateAttr(default=None)
    # Whether validation located the function and proved its form, which a dependency package's step, validated as it is
    # built and again with its consumer's library, then need not do twice.
    _is_function_proven: bool = PrivateAttr(default=False)

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @field_validator("function_name", mode="before")
    @classmethod
    def validate_function_name(cls, function_name: object) -> object:
        """Refuse a `function_name` that is not an import path, such as a flat name of the retired registry."""
        if not isinstance(function_name, str):
            return function_name
        violation = function_name_form_violation(function_name=function_name)
        if violation is not None:
            raise ValueError(violation)
        return nfc(function_name)

    def place_in_tree(self, *, tree_bundle: TreeBundle | None) -> None:
        """Record the member of its method tree the step's bundle was read as, or None for a bundle parsed from a string."""
        self._tree_bundle = tree_bundle

    @property
    def tree_bundle(self) -> TreeBundle | None:
        return self._tree_bundle

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
        """Locate the function's module and prove the function's form from its source, without running Python, once."""
        if self._is_function_proven:
            return
        try:
            self._check_function_statically()
        except (PipeFuncFunctionError, TreePythonError) as exc:
            msg = f"PipeFunc '{self.code}' cannot call its function '{self.function_name}': {exc.message}"
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.PIPE_FUNC_FUNCTION_REFUSED,
                domain_code=self.domain_code,
                pipe_code=self.code,
                field_name="function_name",
            ) from exc
        self._is_function_proven = True

    @override
    def validate_once_built(self) -> None:
        """Locate the function and prove its form: a step whose function cannot be found is one that cannot be built."""
        self.validate_output_with_library()

    def _check_function_statically(self) -> None:
        """Locate the module where the step's import root puts it, prove the function's form, and check the tree's module names.

        A sandbox-hosted deployment imports the function in a sandbox, whose packages are not this process's, so there
        a module name is checked against the standard library only.

        Raises:
            PipeFuncFunctionError: The module is not found, or the form is not proven.
            TreeModuleShadowingError: A top-level module of the tree, or of the submitted Python, would shadow another.
        """
        library_id = get_current_library_id_or_none()
        imports_in_this_process = not is_pipe_func_sandbox_hosted()
        tree_bundle = self._tree_bundle
        module_source: PipeFuncModuleSource
        if tree_bundle is not None:
            tree = tree_bundle.tree
            # A crate loaded on another host carries the tree's files when its library captured them; the tree's
            # directory is then the host that listed it, so the files are read in place of the disk.
            captured = (
                get_library_manager().get_pipe_func_files(library_id=library_id, root_key=tree_bundle.tree_key) if library_id is not None else None
            )
            try:
                module_source = locate_in_tree(function_name=self.function_name, tree=tree, files=captured)
            except OSError as exc:
                msg = f"The module of the function_name '{self.function_name}' cannot be read from the method tree on this host."
                raise PipeFuncFunctionError(msg) from exc
            check_pipe_func_definition(module_source=module_source)
            on_disk = captured is None and tree.directory is not None
            check_tree_module_names(
                top_level_modules=top_level_module_names(tree_paths=captured.keys() if captured is not None else tree.members),
                # Named by the bundle it holds, never by its directory, which is a path on this host.
                tree_label=tree_label_holding(tree_path=tree_bundle.tree_path),
                root=tree.directory.resolve() if on_disk and tree.directory is not None else None,
                checks_this_process=imports_in_this_process,
            )
        elif not imports_in_this_process:
            submitted = (
                get_library_manager().get_pipe_func_files(library_id=library_id, root_key=SUBMITTED_PYTHON_ROOT_KEY)
                if library_id is not None
                else None
            )
            module_source = locate_in_files(function_name=self.function_name, files=submitted or {})
            check_pipe_func_definition(module_source=module_source)
            check_tree_module_names(
                top_level_modules=top_level_module_names(tree_paths=(submitted or {}).keys()),
                tree_label="the Python submitted with the method",
                root=None,
                checks_this_process=False,
            )
        else:
            module_source = locate_on_import_path(function_name=self.function_name)
            check_pipe_func_definition(module_source=module_source)

    def bind_function(self) -> Callable[..., Any]:
        """Import the function in this process and check it, once per holder: the `direct` mode's way to reach it.

        The import is made for the current library, which holds the tree's Python until it is torn down.

        Raises:
            PipeFuncFunctionError: The function cannot be located, its form is not proven, it does not follow the
                calling convention, or its return type disagrees with the step's output.
            TreePythonError: The tree's Python cannot load in this process, such as while another tree's is held.
        """
        holder = get_current_library_id_or_none() or _PROCESS_HOLDER
        bound = self._bound_function
        if bound is not None and bound[0] == holder:
            return bound[1]
        function: Callable[..., Any]
        if self._tree_bundle is not None:
            function = bind_tree_function(
                function_name=self.function_name,
                tree=self._tree_bundle.tree,
                holder=holder,
                tree_label=tree_label_holding(tree_path=self._tree_bundle.tree_path),
            )
        else:
            function = bind_import_path_function(function_name=self.function_name)
        self._check_return_type(function=function)
        self._bound_function = (holder, function)
        return function

    def _check_return_type(self, *, function: Callable[..., Any]) -> None:
        """Check the function's return type against the step's output concept and multiplicity.

        Raises:
            PipeFuncFunctionError: They disagree.
        """
        return_type: type[StuffContent] | None = get_type_hints(function).get("return")
        if return_type is None:
            msg = f"The return type of the function '{self.function_name}' is None. It should be a subclass of StuffContent."
            raise PipeFuncFunctionError(msg)
        if self.output.multiplicity and not issubclass(return_type, ListContent):
            msg = (
                f"PipeFunc '{self.code}' output multiplicity is '{self.output.multiplicity}', but the function '{self.function_name}' "
                f"return type {return_type} is not a subclass of ListContent. The output of your PipeFunc is "
                f"'{self.output.to_bundle_representation()}'. The return type of your function should be a subclass of ListContent."
            )
            raise PipeFuncFunctionError(msg)
        if not self.output.multiplicity and issubclass(return_type, ListContent):
            msg = (
                f"PipeFunc '{self.code}' output multiplicity is '{self.output.multiplicity}', but the function '{self.function_name}' "
                f"return type {return_type} is a subclass of ListContent. The output of your PipeFunc is "
                f"'{self.output.concept.concept_ref}{self.output.to_bundle_representation()}' "
                f"when it should be '{self.output.concept.concept_ref}' (no multiplicity)."
            )
            raise PipeFuncFunctionError(msg)

        # Validate that the function's return type matches the concept's structure class
        concept_structure_class = get_class_registry().get_class(name=self.output.concept.structure_class_name)
        if concept_structure_class is None:
            msg = (
                f"PipeFunc '{self.code}' failed to validate output with library: "
                f"Concept structure class '{self.output.concept.structure_class_name}' not found in registry. "
                f"The class may live in a Python module that was not part of the request — include that module, "
                f"or express the type as MTHDS concepts."
            )
            raise PipeFuncFunctionError(msg)

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

                if not (is_same_class or is_subclass or is_same_name):
                    msg = (
                        f"PipeFunc '{self.code}' output concept expects structure class '{self.output.concept.structure_class_name}' "
                        f"(from {concept_structure_class.__module__}.{concept_structure_class.__name__}), "
                        f"but the function '{self.function_name}' return type is 'ListContent[{item_type.__name__}]' "
                        f"(from {item_type.__module__}.{item_type.__name__}). "
                        f"The item type of your ListContent should be '{self.output.concept.structure_class_name}' or a subclass of it."
                    )
                    raise PipeFuncFunctionError(msg)
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
                raise PipeFuncFunctionError(msg)

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeFuncOutput:
        # In `direct` mode the step runs the function it bound before the run (`_validate_before_run`, a cache hit here),
        # and names it for the in-process executor, since the step may be one no library holds; out of process, the
        # function is imported where the call lands.
        bound_function = None if is_pipe_func_sandbox_hosted() else self._bind_for_run(pipe_run_params=pipe_run_params)
        try:
            with pipe_func_call_in_flight(pipe_ref=self.pipe_ref, function=bound_function) if bound_function is not None else nullcontext():
                execution_result = await get_pipe_func_executor().run_pipe_func(
                    job_metadata=job_metadata,
                    # Qualified: the executor resolves this against the transported library, which is
                    # keyed by pipe_ref. A bare code no longer resolves there.
                    pipe_code=self.pipe_ref,
                    function_name=self.function_name,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                )
        except Exception as exc:
            # PipeFunc runs arbitrary user code — in-process, or (in hosted mode) inside a sandbox
            # reached through a Temporal activity — whose failure surface is not enumerable; any
            # failure is wrapped into a diagnostic PipeRunError below. Re-raises, never swallows.
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
            # Not classified as the caller's fault: the function's own exception text can carry
            # whatever the process holds (a path, a setting, a secret), so it stays redacted under
            # STRICT disclosure.
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        the_content = execution_result.content

        working_memory = store_result(
            memory=working_memory,
            concept=self.output.concept,
            content=the_content,
            result_name=output_name,
        )

        # Capture execution data for the graph tracer. PipeFunc has no prompts or
        # models to record, but the sidepanel should still show *what* function ran
        # and what kind of content it returned — useful for debugging and for
        # distinguishing multiple PipeFunc nodes in a graph. In hosted mode the module/qualname
        # ride back on the execution result (the operator no longer holds the callable).
        execution_data_dict: dict[str, Any] = {
            "function_name": self.function_name,
            "function_module": execution_result.function_module,
            "function_qualname": execution_result.function_qualname or self.function_name,
            "output_content_type": type(the_content).__name__,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeFuncOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
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
        log.debug("The dry run of a PipeFunc validates its inputs and return type without running the function", fields={"pipe_code": self.code})
        # Sandbox-hosted mode: the function is never imported in THIS process (the tree's files travel to the
        # sandbox with the call), so its return type cannot be inspected here. Build the mock output from the
        # DECLARED output concept's structure class instead — mirroring PipeLLM's dry run — and let the sandbox
        # check the real function when it imports it. In direct mode the function was imported and checked
        # before the run (`_validate_before_run`).
        function = None if is_pipe_func_sandbox_hosted() else self._bind_for_run(pipe_run_params=pipe_run_params)
        return_type: type[StuffContent]
        if function is None:
            return_type = get_class_registry().get_required_subclass(
                name=self.output.concept.structure_class_name,
                base_class=StuffContent,
            )
        else:
            hinted_return_type = get_type_hints(function).get("return")
            if hinted_return_type is None:
                msg = f"Dry run of {self.type} '{self.code}' failed: function return type is None; it must be a subclass of StuffContent."
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            return_type = hinted_return_type

        # Without an annotation (hosted mode), `return_type` is the ITEM structure class, so the
        # declared output multiplicity decides the mock's shape; with a live annotation the return
        # type itself already carries the list-ness (`ListContent[...]`), so wrapping again would
        # double-nest.
        mock_multiplicity = (self.output.multiplicity or False) if function is None else False
        stuff_spec = TypedNamedStuffSpec(
            variable_name="mock_output",
            concept=ConceptFactory.make(
                concept_code=self.output.concept.code,
                domain_code="generic",
                description="Lorem Ipsum",
                structure_class_name=self.output.concept.structure_class_name,
            ),
            structure_class=return_type,
            multiplicity=mock_multiplicity,
        )
        mock_content = WorkingMemoryFactory.make_mock_stuff(stuff_spec).content

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
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        if is_pipe_func_sandbox_hosted():
            # Sandbox-hosted mode: the function is never imported in this process; the sandbox imports and checks it.
            return
        self._bind_for_run(pipe_run_params=pipe_run_params)

    def _bind_for_run(self, *, pipe_run_params: PipeRunParams) -> Callable[..., Any]:
        """The function, imported and checked for this run, or a `PipeRunError` on the step saying why it cannot be called."""
        try:
            return self.bind_function()
        except (PipeFuncFunctionError, TreePythonError) as exc:
            msg = f"PipeFunc '{self.code}' cannot call its function '{self.function_name}': {exc.message}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
        except Exception as exc:
            # Importing the function's module runs the method's own module-level code, whose failure surface is not
            # enumerable: an ImportError, the guard's refusal of a file the tree excludes included, or anything the
            # code raises. Wrapped on the step, as a failure of the function itself is, and never swallowed.
            msg = f"PipeFunc '{self.code}' cannot import the module of its function '{self.function_name}': {type(exc).__name__}: {exc}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
