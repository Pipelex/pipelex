import types

from pipelex.tools.typing.module_inspector import find_classes_in_module


class TestFindClassesInModule:
    def test_find_all_classes_no_base_class(self):
        """Test finding all classes when no base class is specified."""
        test_module = types.ModuleType("test_module")

        class ClassA:
            pass

        class ClassB:
            pass

        # Set __module__ so inspect.getmembers finds them
        ClassA.__module__ = test_module.__name__
        ClassB.__module__ = test_module.__name__
        test_module.ClassA = ClassA  # type: ignore[attr-defined]
        test_module.ClassB = ClassB  # type: ignore[attr-defined]
        test_module.some_function = lambda: None  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert ClassA in classes
        assert ClassB in classes

    def test_find_classes_with_base_class(self):
        """Test finding classes that inherit from a specific base class."""
        test_module = types.ModuleType("test_module")

        class BaseClass:
            pass

        class SubClass(BaseClass):
            pass

        class UnrelatedClass:
            pass

        # Set __module__
        BaseClass.__module__ = test_module.__name__
        SubClass.__module__ = test_module.__name__
        UnrelatedClass.__module__ = test_module.__name__
        test_module.BaseClass = BaseClass  # type: ignore[attr-defined]
        test_module.SubClass = SubClass  # type: ignore[attr-defined]
        test_module.UnrelatedClass = UnrelatedClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=BaseClass, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert BaseClass in classes
        assert SubClass in classes
        assert UnrelatedClass not in classes

    def test_find_classes_exclude_imported(self):
        """Test that imported classes are excluded when include_imported=False."""
        test_module = types.ModuleType("test_module")

        class LocalClass:
            pass

        class ImportedClass:
            pass

        LocalClass.__module__ = test_module.__name__
        ImportedClass.__module__ = "other_module"
        test_module.LocalClass = LocalClass  # type: ignore[attr-defined]
        test_module.ImportedClass = ImportedClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 1
        assert len(classes) == expected_number_of_classes
        assert LocalClass in classes
        assert ImportedClass not in classes

    def test_find_classes_include_imported(self):
        """Test that imported classes are included when include_imported=True."""
        test_module = types.ModuleType("test_module")

        class LocalClass:
            pass

        class ImportedClass:
            pass

        LocalClass.__module__ = test_module.__name__
        ImportedClass.__module__ = "other_module"
        test_module.LocalClass = LocalClass  # type: ignore[attr-defined]
        test_module.ImportedClass = ImportedClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=True)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert LocalClass in classes
        assert ImportedClass in classes

    def test_find_classes_empty_module(self):
        """Test finding classes in an empty module."""
        test_module = types.ModuleType("test_module")
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 0
        assert len(classes) == expected_number_of_classes

    def test_find_classes_with_functions_and_variables(self):
        """Test that functions and variables are not included in class search."""
        test_module = types.ModuleType("test_module")

        class TestClass:
            pass

        TestClass.__module__ = test_module.__name__

        def test_function():
            pass

        test_module.TestClass = TestClass  # type: ignore[attr-defined]
        test_module.test_function = test_function  # type: ignore[attr-defined]
        test_module.some_variable = 42  # type: ignore[attr-defined]
        test_module.some_string = "hello"  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 1
        assert len(classes) == expected_number_of_classes
        assert TestClass in classes

    def test_find_classes_with_nested_classes(self):
        """Test finding classes including nested classes."""
        test_module = types.ModuleType("test_module")

        class OuterClass:
            class InnerClass:
                pass

        OuterClass.__module__ = test_module.__name__
        test_module.OuterClass = OuterClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 1
        assert len(classes) == expected_number_of_classes
        assert OuterClass in classes

    def test_find_classes_with_builtin_types(self):
        """Test finding classes including user-defined types (not builtins, which can't be assigned __module__)."""
        test_module = types.ModuleType("test_module")

        class MyClassA:
            pass

        class MyClassB:
            pass

        MyClassA.__module__ = test_module.__name__
        MyClassB.__module__ = test_module.__name__
        test_module.MyClassA = MyClassA  # type: ignore[attr-defined]
        test_module.MyClassB = MyClassB  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert MyClassA in classes
        assert MyClassB in classes

    def test_find_classes_with_base_class_and_imported(self):
        test_module = types.ModuleType("test_module")

        class BaseClass:
            pass

        class LocalSubClass(BaseClass):
            pass

        class ImportedSubClass(BaseClass):
            pass

        BaseClass.__module__ = test_module.__name__
        LocalSubClass.__module__ = test_module.__name__
        ImportedSubClass.__module__ = "other_module"
        test_module.BaseClass = BaseClass  # type: ignore[attr-defined]
        test_module.LocalSubClass = LocalSubClass  # type: ignore[attr-defined]
        test_module.ImportedSubClass = ImportedSubClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=BaseClass, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert BaseClass in classes
        assert LocalSubClass in classes
        assert ImportedSubClass not in classes
        classes = find_classes_in_module(test_module, base_class=BaseClass, include_imported=True)
        expected_number_of_classes = 3
        assert len(classes) == expected_number_of_classes
        assert BaseClass in classes
        assert LocalSubClass in classes
        assert ImportedSubClass in classes
