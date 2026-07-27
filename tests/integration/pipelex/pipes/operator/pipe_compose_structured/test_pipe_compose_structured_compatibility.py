"""Integration tests for PipeCompose direct StructuredContent class compatibility.

These tests verify class compatibility scenarios when composing StructuredContent
objects directly (not TextContent, not ListContent):
- Exact type match: Person -> Person field
- Class equivalence: Employee -> Person field (structurally equivalent)
- Subclass to base: Manager -> Person field
- Incompatible classes: Location -> Person field (should fail)
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.exceptions import PipeComposeError
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.models_for_pipe_compose import (
    Employee,
    Location,
    Manager,
    Person,
)
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.test_data import StructuredCompatibilityTestData


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeStructuredCompatibility:
    """Integration tests for direct StructuredContent class compatibility in PipeCompose."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the test library for these tests."""
        return [Path("tests/integration/pipelex/pipes/operator/pipe_compose_structured")]

    async def test_exact_type_match(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that exact type match works: Person -> Person field."""
        load_test_library(test_library_path)

        # Create working memory with a Person object
        person = Person(name="Alice", role="Developer")
        person_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=person,
            name="input_person",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="input_person", stuff=person_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose PersonHolder with exact Person type",
                "inputs": {"input_person": "Text"},
                "construct": StructuredCompatibilityTestData.EXACT_TYPE_CONSTRUCT,
                "output": "compose_structured_test.PersonHolder",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_exact_type",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "PersonHolder"

        holder = main_stuff.content
        assert holder.holder_name == "Exact Type Holder"  # type: ignore[attr-defined]
        assert isinstance(holder.person, Person)  # type: ignore[attr-defined]
        assert holder.person.name == "Alice"  # type: ignore[attr-defined]
        assert holder.person.role == "Developer"  # type: ignore[attr-defined]

        pretty_print(holder, title="PersonHolder - Exact type match (Person -> Person)")

    async def test_equivalent_class_employee_to_person(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that structurally equivalent classes are converted: Employee -> Person field."""
        load_test_library(test_library_path)

        # Create working memory with an Employee object (structurally equivalent to Person)
        employee = Employee(name="Bob", role="Designer")
        employee_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=employee,
            name="input_employee",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="input_employee", stuff=employee_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose PersonHolder with structurally equivalent Employee",
                "inputs": {"input_employee": "Text"},
                "construct": StructuredCompatibilityTestData.EQUIVALENT_CLASS_CONSTRUCT,
                "output": "compose_structured_test.PersonHolder",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_equivalent_class",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "PersonHolder"

        holder = main_stuff.content
        assert holder.holder_name == "Equivalent Class Holder"  # type: ignore[attr-defined]
        # The person field should now be a Person instance (rebuilt from Employee)
        assert type(holder.person).__name__ == "Person"  # type: ignore[attr-defined]
        assert holder.person.name == "Bob"  # type: ignore[attr-defined]
        assert holder.person.role == "Designer"  # type: ignore[attr-defined]

        pretty_print(holder, title="PersonHolder - Class equivalence (Employee -> Person)")

    async def test_reverse_equivalent_class_person_to_employee(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test reverse equivalence: Person -> Employee field."""
        load_test_library(test_library_path)

        # Create working memory with a Person object
        person = Person(name="Carol", role="Manager")
        person_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=person,
            name="input_person",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="input_person", stuff=person_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose EmployeeHolder with structurally equivalent Person",
                "inputs": {"input_person": "Text"},
                "construct": StructuredCompatibilityTestData.REVERSE_EQUIVALENT_CONSTRUCT,
                "output": "compose_structured_test.EmployeeHolder",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_reverse_equivalent",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "EmployeeHolder"

        holder = main_stuff.content
        assert holder.holder_name == "Reverse Equivalent Holder"  # type: ignore[attr-defined]
        # The employee field should now be an Employee instance (rebuilt from Person)
        assert type(holder.employee).__name__ == "Employee"  # type: ignore[attr-defined]
        assert holder.employee.name == "Carol"  # type: ignore[attr-defined]
        assert holder.employee.role == "Manager"  # type: ignore[attr-defined]

        pretty_print(holder, title="EmployeeHolder - Reverse equivalence (Person -> Employee)")

    async def test_subclass_to_base_manager_to_person(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that subclass is accepted when field expects base class: Manager -> Person field."""
        load_test_library(test_library_path)

        # Create working memory with a Manager object (subclass of Person)
        manager = Manager(name="Dave", role="Director", department="Engineering")
        manager_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=manager,
            name="input_manager",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="input_manager", stuff=manager_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose PersonHolder with Manager subclass",
                "inputs": {"input_manager": "Text"},
                "construct": StructuredCompatibilityTestData.SUBCLASS_TO_BASE_CONSTRUCT,
                "output": "compose_structured_test.PersonHolder",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_subclass_to_base",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "PersonHolder"

        holder = main_stuff.content
        assert holder.holder_name == "Subclass to Base Holder"  # type: ignore[attr-defined]
        # The person field accepts the Manager subclass
        assert isinstance(holder.person, Person)  # type: ignore[attr-defined]
        assert holder.person.name == "Dave"  # type: ignore[attr-defined]
        assert holder.person.role == "Director"  # type: ignore[attr-defined]
        # Subclass-specific fields should be preserved
        assert hasattr(holder.person, "department")  # type: ignore[attr-defined]
        assert holder.person.department == "Engineering"  # type: ignore[attr-defined]

        pretty_print(holder, title="PersonHolder - Subclass to base (Manager -> Person)")

    async def test_incompatible_classes_raises_error(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that incompatible classes raise an error: Location -> Person field."""
        load_test_library(test_library_path)

        # Create working memory with a Location object (incompatible with Person)
        location = Location(latitude=48.8566, longitude=2.3522, name="Paris")
        location_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=location,
            name="input_location",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="input_location", stuff=location_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose PersonHolder with incompatible Location",
                "inputs": {"input_location": "Text"},
                "construct": StructuredCompatibilityTestData.INCOMPATIBLE_CONSTRUCT,
                "output": "compose_structured_test.PersonHolder",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_incompatible",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # The composition should fail because Location cannot be converted to Person
        with pytest.raises(PipeComposeError, match="Cannot convert"):
            await get_pipe_router().run(pipe_job=pipe_job)
